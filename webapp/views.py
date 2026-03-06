from django.shortcuts import render
import  numpy as np
from django.http import StreamingHttpResponse, Http404
from django.shortcuts import  get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
import cv2, os
from django.conf import settings
from django.db.models import Q
import time
from django.db.models.functions import Trim
from webapp import views
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Employee, FaceRecording ,RecognizedFace,Rule
from datetime import date, datetime, timedelta
from calendar import monthrange
from django.db.models.functions import TruncDate, TruncMonth, ExtractYear
import json
from django.core.paginator import Paginator
from .models import EmailSend
import csv


def index(request):
    COMPANY_ID = "1060"

    # ================= BASIC COUNTS =================
    employees = Employee.objects.filter(company_id=COMPANY_ID)

    total_employees = employees.count()
    total_cameras = len(views.streams)

    # ================= TODAY PRESENT =================
    today = date.today()
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())

    today_present = (
        RecognizedFace.objects
        .filter(capture_date_time__range=(start_dt, end_dt))
        .exclude(emp_id__isnull=True)
        .exclude(emp_id="")
        .values("emp_id")
        .distinct()
        .count()
    )

    attendance_percentage = (
        round((today_present / total_employees) * 100, 2)
        if total_employees else 0
    )

    # =========================================================
    # WEEK DATA
    # =========================================================
    start_week = today - timedelta(days=today.weekday())

    week_labels = []
    week_values = []

    for i in range(7):
        day = start_week + timedelta(days=i)

        count = (
            RecognizedFace.objects
            .filter(capture_date_time__date=day)
            .exclude(emp_id__isnull=True)
            .exclude(emp_id="")
            .values("emp_id")
            .distinct()
            .count()
        )

        percent = round((count / total_employees) * 100, 1) if total_employees else 0

        week_labels.append(day.strftime("%A"))
        week_values.append(percent)

    # =========================================================
    # MONTH DATA
    # =========================================================
    import calendar

    month_labels = []
    month_values = []

    current_year = today.year

    for m in range(1, 13):

        days_in_month = calendar.monthrange(current_year, m)[1]

        total_present = (
            RecognizedFace.objects
            .filter(
                capture_date_time__year=current_year,
                capture_date_time__month=m
            )
            .exclude(emp_id__isnull=True)
            .exclude(emp_id="")
            .values("capture_date_time__date", "emp_id")
            .distinct()
            .count()
        )

        max_possible = total_employees * days_in_month

        if max_possible > 0:
            percent = round((total_present / max_possible) * 100, 1)
        else:
            percent = 0

        month_labels.append(datetime(2000, m, 1).strftime("%b"))
        month_values.append(percent)

    # =========================================================
    # YEAR DATA (last 7 years)
    # =========================================================
    year_labels = []
    year_values = []

    for y in range(current_year - 6, current_year + 1):

        total_present = (
            RecognizedFace.objects
            .filter(capture_date_time__year=y)
            .exclude(emp_id__isnull=True)
            .exclude(emp_id="")
            .values("capture_date_time__date", "emp_id")
            .distinct()
            .count()
        )

        days_in_year = 366 if calendar.isleap(y) else 365
        max_possible = total_employees * days_in_year

        if max_possible > 0:
            percent = round((total_present / max_possible) * 100, 1)
        else:
            percent = 0

        year_labels.append(str(y))
        year_values.append(percent)
        
    # ================= CAMERA DROPDOWN =================
    camera_names = list(views.streams.keys())

    month_list = [
    {"num":1,"name":"Jan"},
    {"num":2,"name":"Feb"},
    {"num":3,"name":"Mar"},
    {"num":4,"name":"Apr"},
    {"num":5,"name":"May"},
    {"num":6,"name":"Jun"},
    {"num":7,"name":"Jul"},
    {"num":8,"name":"Aug"},
    {"num":9,"name":"Sep"},
    {"num":10,"name":"Oct"},
    {"num":11,"name":"Nov"},
    {"num":12,"name":"Dec"},
    ]


    # ================= CONTEXT =================
    context = {
        "employees": employees,

        "total_employees": total_employees,
        "company_id": COMPANY_ID,
        "total_cameras": total_cameras,

        "present_count": today_present,
        "attendance_percentage": attendance_percentage,

        "week_labels": json.dumps(week_labels),
        "week_values": json.dumps(week_values),

        "month_labels": json.dumps(month_labels),
        "month_values": json.dumps(month_values),

        "year_labels": json.dumps(year_labels),
        "year_values": json.dumps(year_values),
        
        "camera_names":camera_names,
        "month_list":month_list,

    }

    return render(request, "webapp/index.html", context)

def camera_chart_api(request):

    camera = request.GET.get("camera")
    month = request.GET.get("month")

    if not camera or not month:
        return JsonResponse({"emp":0,"unknown":0,"noface":0})

    records = RecognizedFace.objects.filter(
        camera_name=camera,
        capture_date_time__month=month
    )

    total = records.count()

    if total == 0:
        return JsonResponse({"emp":0,"unknown":0,"noface":0})

    emp = records.exclude(emp_id__isnull=True).exclude(emp_id="").count()
    unknown = records.filter(similarity_id="UNKNOWN").count()
    noface = records.filter(similarity_id="NO_FACE").count()

    return JsonResponse({
        "emp": emp,
        "unknown": unknown,
        "noface": noface,
    })


#--------------Face Register--------------------
def face_register(request):
    if request.method != "POST":
        return render(request, 'webapp/face_register.html')

    company_id  = request.POST.get('company_id', '').strip()
    emp_name    = request.POST.get('emp_name', '').strip()
    emp_id      = request.POST.get('emp_id', '').strip()
    emp_type    = request.POST.get('emp_type', '').strip()
    dept        = request.POST.get('dept', '').strip()
    designation = request.POST.get('designation', '').strip()
    profile_pic = request.FILES.get("profile_pic")
    agree_terms = request.POST.get('agree_terms') == 'on'

    if not (company_id and emp_name and emp_id):
        return JsonResponse({"error": "Missing required fields"}, status=400)

    if Employee.objects.filter(company_id=company_id, emp_id=emp_id).exists():
        return JsonResponse({"error": "Employee already exists"}, status=409)

    employee = Employee.objects.create(
        company_id=company_id,
        emp_name=emp_name,
        emp_id=emp_id,
        emp_type=emp_type,
        dept=dept,
        designation=designation,
        profile_pic=profile_pic,
        agree_terms=agree_terms
    )

    return JsonResponse({
        "success": True,
        "employee_db_id": employee.id
    })


#--------------Face Record--------------------

def face_record(request, employee_db_id):
    employee = Employee.objects.filter(id=employee_db_id).first()
    if not employee:
        return HttpResponse("Employee not found", status=404)

    return render(
        request,
        "webapp/face_record.html",
        {
            "emp_name": employee.emp_name,
            "emp_id": employee.emp_id
        }
    )


def upload_face_video(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method"})

    emp_id = request.POST.get("employee_id")
    file = request.FILES.get("video")

    if not emp_id or not file:
        return JsonResponse({"success": False, "error": "Missing data"})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{emp_id}_{timestamp}.webm"

    upload_dir = os.path.join(settings.MEDIA_ROOT, "face_videos")
    os.makedirs(upload_dir, exist_ok=True)

    filepath = os.path.join(upload_dir, filename)

    with open(filepath, "wb+") as dest:
        for chunk in file.chunks():
            dest.write(chunk)

    FaceRecording.objects.create(
        emp_id=emp_id,
        video_filename=filename,
        video_path=f"face_videos/{filename}"  #MEDIA serving
    )

    return JsonResponse({"success": True})


#--------------Recognized Faces--------------------
streams = {}   

def camera_index(request):
    """
    Show available camera names
    """
    return render(
        request,
        "webapp/camera_index.html",
        {"camera_names": streams.keys()}
    )


def gen_frames(name):
    """
    Yield JPEG frames from running CameraWorker
    """
    try:
        worker = streams.get(name)
        if not worker:
            print(f"⚠️ No active stream found for '{name}'")
            return

        while True:
            frame_bytes = worker.get_jpeg()
            if not frame_bytes:
                time.sleep(0.05)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                frame_bytes +
                b"\r\n"
            )

    except (BrokenPipeError, ConnectionResetError):
        print(f"🔌 [{name}] Client disconnected")
    except GeneratorExit:
        print(f"🧹 [{name}] Stream closed")
    except Exception as e:
        print(f"⚠️ [{name}] Stream error: {e}")


def video_feed(request, name):
    """
    Return MJPEG stream for a camera
    """
    if name not in streams:
        raise Http404("Camera not found")

    response = StreamingHttpResponse(
        gen_frames(name),
        content_type="multipart/x-mixed-replace; boundary=frame"
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    print(f"🎥 [{name}] Stream started for {request.META.get('REMOTE_ADDR')}")
    return response


#--------------Emp Tracking--------------------
def track_employee(request):
    
    mode = request.GET.get("mode")
    # mode = all | track | similar | unknown

    records = []
    results = []
    searched_emp_id = None
    searched_date = None
    searched_emp_name = None

    
    # SHOW ALL RECORDS
    if mode == "all":
        records = RecognizedFace.objects.all().order_by("-capture_date_time")

    # REVIEW SIMILAR
    elif mode == "similar":
        records = RecognizedFace.objects.filter(
            similarity_id__isnull=False
        ).order_by("-capture_date_time")

    # REVIEW UNKNOWN
    elif mode == "unknown":
        records = RecognizedFace.objects.filter(
            emp_id__isnull=True,
            similarity_id__isnull=True
        ).order_by("-capture_date_time")

   
    # TRACK EMPLOYEE
    today = date.today()           # or datetime.date.today()

    if request.method == "POST":
        emp_id = request.POST.get("emp_id")
        selected_date = request.POST.get("date")

        if emp_id and selected_date:
            try:
                date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
            except ValueError:
                date_obj = today   # fallback if invalid date

            searched_emp_id = emp_id
            searched_date = date_obj
            
            emp = Employee.objects.filter(emp_id=emp_id).first()
            searched_emp_name = emp.emp_name if emp else "Unknown"
            
            qs = RecognizedFace.objects.filter(
                emp_id=emp_id,
                capture_date_time__date=date_obj
            ).order_by("capture_date_time")

            camera_map = {}
            for row in qs:
                camera_map.setdefault(row.camera_name, []).append(row)

            for cam_name, captures in camera_map.items():
                first = captures[0]
                last = captures[-1] if len(captures) > 1 else None

                results.append({
                    "camera_name": cam_name,
                    "first_time": first.capture_date_time,
                    "first_img": first.image_path,
                    "last_time": last.capture_date_time if last else None,
                })

    return render(
        request,
        "webapp/track.html",
        {
            "records": records,
            "results": results,
            "mode": mode,
            "searched_emp_id": searched_emp_id,
            "searched_date": searched_date,
            "searched_emp_name": searched_emp_name,
            "today": today,
        }
    )


#--------------Detected Face--------------------
def detected_faces(request):
    results = []
    searched = None
    today = date.today()

    cameras = (
        RecognizedFace.objects
        .annotate(cam=Trim("camera_name"))
        .values_list("cam", flat=True)
        .distinct()
        .order_by("cam")
    )

    if request.GET.get("date"):
        date_input = request.GET.get("date")
        camera = request.GET.get("camera")
        face_type = request.GET.get("type")
        
        if date_input:
            try:
                query_date = date.fromisoformat(date_input)
            except (ValueError, TypeError):
                query_date = today  # fallback on invalid date format
        else:
            query_date = today
        
        display_date = query_date.strftime("%Y-%m-%d")
        
        searched = {
        "date": display_date,
        "camera": "All Cameras" if camera == "all" else camera,
        "type": (
            "All Employees" if face_type == "employees" else
            "Unknown" if face_type == "unknown" else
            "All Types"
        ),
    }
    
        qs = RecognizedFace.objects.filter(
            capture_date_time__date=query_date
        ).exclude(similarity_id="NO_FACE")
        
        # 🔹 Collect all detected employee IDs
        emp_ids = (
            qs.filter(emp_id__isnull=False)
            .values_list("emp_id", flat=True)
            .distinct()
        )

        # 🔹 Build emp_id → emp_name map (single DB hit)
        emp_map = {
            e.emp_id: e.emp_name
            for e in Employee.objects.filter(emp_id__in=emp_ids, status="active")
        }

        if camera and camera != "all":
            qs = qs.filter(camera_name__icontains=camera)

        # 🔹 Type filter
        if face_type == "employees":
            qs = qs.filter(emp_id__isnull=False)

        elif face_type == "unknown":
            qs = qs.filter(similarity_id="UNKNOWN")

        else:
            qs = qs.filter(
                Q(emp_id__isnull=False) |
                Q(similarity_id="UNKNOWN")
            )

        qs = qs.order_by("capture_date_time")

        track_map = {}   # ONLY for employees

        for r in qs:
            cam = r.camera_name.strip()

            #EMPLOYEE → group
            if r.emp_id:
                key = (cam, r.emp_id)

                if key not in track_map:
                    track_map[key] = {
                        "emp_id": r.emp_id,
                        "emp_name": emp_map.get(r.emp_id, ""),
                        "camera": cam,
                        "first_time": r.capture_date_time,
                        "last_time": None,
                        "image": r.image_path,
                    }
                else:
                    diff = (r.capture_date_time - track_map[key]["first_time"]).total_seconds()
                    if diff >= 600:
                        track_map[key]["last_time"] = r.capture_date_time

            # UNKNOWN → NO grouping
            else:
                results.append({
                    "emp_id": "UNKNOWN",
                    "emp_name": "",
                    "camera": cam,
                    "first_time": r.capture_date_time,
                    "last_time": None,   
                    "image": r.image_path,
                })

        # merge employee groups + unknown rows
        results = list(track_map.values()) + results

    return render(
        request,
        "webapp/detected_faces.html",
        {
            "results": results,
            "cameras": cameras,
            "searched": searched,
            "today": today,
        }
    )

#--------------No Face--------------------
def no_face(request):
    results = []
    searched = None
    today = date.today()

    cameras = (
        RecognizedFace.objects
        .annotate(cam=Trim("camera_name"))
        .values_list("cam", flat=True)
        .distinct()
        .order_by("cam")
    )

    if request.GET.get("date"):
        date_input = request.GET.get("date")
        camera = request.GET.get("camera")
        
        if date_input:
            try:
                query_date = date.fromisoformat(date_input)
            except (ValueError, TypeError):
                query_date = today
        else:
            query_date = today

        searched = {
            "date": query_date.strftime("%Y-%m-%d"),
            "camera": camera if camera and camera != "all" else "All Cameras",
        }

        qs = RecognizedFace.objects.filter(
            similarity_id="NO_FACE",
            capture_date_time__date=query_date
        )

        if camera and camera != "all":
            qs = qs.filter(camera_name__icontains=camera)

        qs = qs.order_by("capture_date_time")

        # NO grouping for NO_FACE
        for r in qs:
            results.append({
                "emp_id": "NO FACE",
                "camera": r.camera_name.strip(),
                "first_time": r.capture_date_time,
                "last_time": None,   
                "image": r.image_path,
            })

    return render(
        request,
        "webapp/no_face.html",
        {
            "results": results,
            "cameras": cameras,
            "searched": searched,
            "today": today,
        }
    )


#--------------Employee List--------------------
def employee_list(request):
    query = request.GET.get("q", "").strip()

    employees = Employee.objects.filter(status="active").order_by("id")

    if query:
        employees = employees.filter(emp_id__icontains=query)

    return render(request, "webapp/employee_list.html", {
        "employees": employees,
        "query": query
    })


#--------------Employee Edit--------------------
def employee_edit(request, pk):
    employee = get_object_or_404(Employee, pk=pk)

    if request.method == "POST":
        employee.emp_name = request.POST.get("emp_name")
        employee.dept = request.POST.get("dept")
        employee.emp_type = request.POST.get("emp_type")

        if request.FILES.get("profile_pic"):
            employee.profile_pic = request.FILES.get("profile_pic")

        employee.save()
        return redirect("employee_list")

    return render(request, "webapp/employee_edit.html", {
        "employee": employee
    })

#--------------Employee Delete--------------------
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    employee.status = "inactive"
    employee.save()
    return redirect("employee_list")


#--------------Attenadace--------------------
def attendance_page(request):
    date_str = request.GET.get("date")

    # ✅ If no date selected → use today's date
    if not date_str:
        selected_date = date.today()
        date_str = selected_date.strftime("%Y-%m-%d")
    else:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    start_dt = datetime.combine(selected_date, datetime.min.time())
    end_dt   = datetime.combine(selected_date, datetime.max.time())

    attendance = []

    records = (
        RecognizedFace.objects
        .filter(
            capture_date_time__range=(start_dt, end_dt),
            emp_id__isnull=False
        )
        .exclude(emp_id__in=["", "UNKNOWN", "NO_FACE"])
        .order_by("emp_id", "capture_date_time")
    )

    emp_map = {}

    for r in records:
        emp_map.setdefault(r.emp_id, []).append(r)

    for emp_id, recs in emp_map.items():
        first = recs[0]
        last  = recs[-1]

        employee = Employee.objects.filter(emp_id=emp_id).first()
        emp_name = employee.emp_name if employee else "-"

        check_out_time = None
        check_out_cam = None
        total_hours = "-"

        if len(recs) > 1:
            check_out_time = last.capture_date_time
            check_out_cam = last.camera_name
            total_hours = str(last.capture_date_time - first.capture_date_time).split(".")[0]

        attendance.append({
            "emp_id": emp_id,
            "emp_name": emp_name,
            "image": first.image_path,
            "check_in_time": first.capture_date_time,
            "check_in_cam": first.camera_name,
            "check_out_time": check_out_time,
            "check_out_cam": check_out_cam,
            "total_hours": total_hours,
        })

    return render(request, "webapp/attendance.html", {
        "attendance": attendance,
        "selected_date": date_str
    })


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        # simple hardcoded login (as you requested)
        if username == "admin" and password == "admin@123":
            request.session["logged_in"] = True
            return redirect("create_rule")

        return render(request, "webapp/login.html", {
            "error": "Invalid username or password"
        })

    return render(request, "webapp/login.html")


# ---------------- CREATE RULE (STEP 1: ONLY BOX UI) ----------------
def create_rule(request):
    if not request.session.get("logged_in"):
        return redirect("login")

    return render(request, "webapp/create_rule.html")


#---------------------MEETING RULE----------------------------
def create_meeting_rule(request):
    # get or create meeting rule row
    rule_obj, _ = Rule.objects.get_or_create(
        rule_type="meeting",
        defaults={"rules_json": {}}
    )

    rules = rule_obj.rules_json or {}

    # ---------- SAVE ----------
    if request.method == "POST":
        rule_no = f"rule_{len(rules) + 1}"

        rules[rule_no] = {
            "date": request.POST.get("date"),
            "start_time": request.POST.get("start_time"),
            "end_time": request.POST.get("end_time"),
            "department": request.POST.getlist("department"),
            "place": request.POST.getlist("place"),
            "head_email": request.POST.get("head_email"),
            "active": request.POST.get("active") == "true"
        }

        rule_obj.rules_json = rules
        rule_obj.save()
        return redirect("create_meeting_rule")

    # ---------- DROPDOWNS ----------
    departments = (
        Employee.objects
        .values_list("dept", flat=True)
        .distinct()
        .order_by("dept")
    )

    # camera names (NO duplicates)
    from webapp.views import streams
    cameras = list(streams.keys())
    
    #FETCH MEETING RECORDS FROM DATABASE
    meeting_records = EmailSend.objects.filter(
        rule_category="Meeting Rule"
    ).order_by("-created_at")

    return render(request, "webapp/create_meeting_rule.html", {
        "departments": departments,
        "cameras": cameras,
        "rules": rules,
        "meeting_records": meeting_records
    })


def toggle_meeting_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="meeting")
    rules = rule_obj.rules_json

    if rule_key in rules:
        rules[rule_key]["active"] = not rules[rule_key]["active"]
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_meeting_rule")

def delete_meeting_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="meeting")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        del rules[rule_key]
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_meeting_rule")

#----------------ALLOWED PLACE RULE------------------
def create_allowed_place_rule(request):
    rule_obj, _ = Rule.objects.get_or_create(
        rule_type="allowed_place",
        defaults={"rules_json": {}}
    )

    rules = rule_obj.rules_json or {}

    if request.method == "POST":
        rule_no = f"rule_{len(rules) + 1}"

        # --------- Save Rule ---------
        rules[rule_no] = {
            "department": request.POST.getlist("department"),
            "place": request.POST.getlist("place"),
            "head_email": request.POST.get("head_email"),
            "active": request.POST.get("active") == "true",
            "time_mode": request.POST.get("time_mode"),
            "start_time": request.POST.get("start_time"),
            "end_time": request.POST.get("end_time"),
            "zone_type": request.POST.get("zone_type")
        }

        rule_obj.rules_json = rules
        rule_obj.save()
        return redirect("create_allowed_place_rule")

    departments = Employee.objects.values_list("dept", flat=True).distinct()
    from webapp.views import streams
    cameras = list(streams.keys())

    return render(request, "webapp/create_allowed_place_rule.html", {
        "departments": departments,
        "cameras": cameras,
        "rules": rules
    })

def toggle_allowed_place_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="allowed_place")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        rules[rule_key]["active"] = not rules[rule_key].get("active", False)
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_allowed_place_rule")

def delete_allowed_place_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="allowed_place")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        del rules[rule_key]
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_allowed_place_rule")


#----------------RESTRICTED ZONE RULE------------------
def create_restricted_zone_rule(request):
    rule_obj, _ = Rule.objects.get_or_create(
        rule_type="restricted_zone",
        defaults={"rules_json": {}}
    )

    rules = rule_obj.rules_json or {}

    if request.method == "POST":
        rule_no = f"rule_{len(rules) + 1}"
         
        rules[rule_no] = {
            "restricted_departments": request.POST.getlist("department"),
            "place": request.POST.getlist("place"),
            "head_email": request.POST.get("head_email"),
            "active": request.POST.get("active") == "true",
            "time_mode": request.POST.get("time_mode"),
            "start_time": request.POST.get("start_time"),
            "end_time": request.POST.get("end_time"),
            "zone_type": request.POST.get("zone_type"),
        }

        rule_obj.rules_json = rules
        rule_obj.save()
        return redirect("create_restricted_zone_rule")

    departments = Employee.objects.values_list("dept", flat=True).distinct()
    from webapp.views import streams
    cameras = list(streams.keys())

    return render(request,"webapp/create_restricted_zone_rule.html",{
        "departments":departments,
        "cameras":cameras,
        "rules":rules
    })

def toggle_restricted_zone_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="restricted_zone")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        rules[rule_key]["active"] = not rules[rule_key].get("active", False)
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_restricted_zone_rule")


def delete_restricted_zone_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="restricted_zone")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        del rules[rule_key]
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_restricted_zone_rule")


#----------------IN/OUT TIME RULE------------------
def create_inout_time_rule(request):
    rule_obj, _ = Rule.objects.get_or_create(
        rule_type="inout_time",
        defaults={"rules_json": {}}
    )

    rules = rule_obj.rules_json or {}

    if request.method == "POST":
        rule_no = f"rule_{len(rules) + 1}"

        # 🔁 MULTIPLE BREAKS
        breaks = []
        break_names = request.POST.getlist("break_name[]")
        break_starts = request.POST.getlist("break_start[]")
        break_ends = request.POST.getlist("break_end[]")
        break_places = request.POST.getlist("break_place[]")

        for i in range(len(break_names)):
            breaks.append({
                "name": break_names[i],
                "start": break_starts[i],
                "end": break_ends[i],
                "place": break_places[i].split(",")
            })

        rules[rule_no] = {
            "attendance": {
                "in_before": request.POST.get("in_before"),
                "out_after": request.POST.get("out_after"),
                "place": request.POST.getlist("attendance_place[]"),
            },

            "breaks": breaks,
            "head_email": request.POST.get("head_email"),
            "active": request.POST.get("active") == "true"
        }

        rule_obj.rules_json = rules
        rule_obj.save()
        return redirect("create_inout_time_rule")

    from webapp.views import streams
    cameras = list(streams.keys())

    return render(request, "webapp/create_inout_time_rule.html", {
        "rules": rules,
        "cameras": cameras
    })


def toggle_inout_time_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="inout_time")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        rules[rule_key]["active"] = not rules[rule_key]["active"]
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_inout_time_rule")


def delete_inout_time_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="inout_time")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        del rules[rule_key]
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_inout_time_rule")

#-----------------UNKNOW PERSON ALERT-------------------
def create_unknown_alert_rule(request):
    rule_obj, _ = Rule.objects.get_or_create(
        rule_type="unknown_alert",
        defaults={"rules_json": {}}
    )

    rules = rule_obj.rules_json or {}

    if request.method == "POST":
        rules["rule_1"] = {
            "head_email": request.POST.get("head_email"),
            "active": request.POST.get("active") == "true"
        }

        rule_obj.rules_json = rules
        rule_obj.save()
        return redirect("create_unknown_alert_rule")
    
    unknown_records = EmailSend.objects.filter(
        rule_category="Unknown Person"
    ).order_by("-created_at")

    return render(request, "webapp/create_unknown_alert_rule.html", {
        "rule": rules.get("rule_1"),
        "unknown_records": unknown_records
    })


def toggle_unknown_alert_rule(request):
    rule_obj = Rule.objects.get(rule_type="unknown_alert")
    rules = rule_obj.rules_json or {}

    rules["rule_1"]["active"] = not rules["rule_1"]["active"]

    rule_obj.rules_json = rules
    rule_obj.save()

    return redirect("create_unknown_alert_rule")

def delete_unknown_alert_rule(request):
    try:
        rule_obj = Rule.objects.get(rule_type="unknown_alert")
    except Rule.DoesNotExist:
        return redirect("create_unknown_alert_rule")

    rule_obj.rules_json = {}   # 🔥 clear rule
    rule_obj.save()

    return redirect("create_unknown_alert_rule")

#-----------------PHONE USAGE ALERT-------------------
def create_phone_usage_rule(request):
    rule_obj, _ = Rule.objects.get_or_create(
        rule_type="phone_usage",
        defaults={"rules_json": {}}
    )

    rules = rule_obj.rules_json or {}

    if request.method == "POST":
        rule_no = f"rule_{len(rules) + 1}"

        rules[rule_no] = {
            "place": request.POST.getlist("place"),   # multi camera
            "head_email": request.POST.get("head_email"),
            "active": request.POST.get("active") == "true"
        }

        rule_obj.rules_json = rules
        rule_obj.save()
        return redirect("create_phone_usage_rule")

    cameras = list(streams.keys())

    return render(request, "webapp/phone_usage_rule.html", {
        "rules": rules,
        "cameras": cameras
    })

def toggle_phone_usage_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="phone_usage")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        rules[rule_key]["active"] = not rules[rule_key].get("active", False)
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_phone_usage_rule")

def delete_phone_usage_rule(request, rule_key):
    rule_obj = Rule.objects.get(rule_type="phone_usage")
    rules = rule_obj.rules_json or {}

    if rule_key in rules:
        del rules[rule_key]
        rule_obj.rules_json = rules
        rule_obj.save()

    return redirect("create_phone_usage_rule")


#-----------------GROUP GATHERING-------------------
def create_group_gathering_rule(request):
    rule_obj,_=Rule.objects.get_or_create(
        rule_type="group_gathering",
        defaults={"rules_json":{}}
    )

    rules=rule_obj.rules_json or {}

    if request.method=="POST":
        rule_no=f"rule_{len(rules)+1}"

        rules[rule_no]={
            "place":request.POST.getlist("place"),
            "max_count":int(request.POST.get("max_count")),
            "head_email":request.POST.get("head_email"),
            "active":request.POST.get("active")=="true"
        }

        rule_obj.rules_json=rules
        rule_obj.save()
        return redirect("create_group_gathering_rule")

    from webapp.views import streams
    cameras=list(streams.keys())

    return render(request,"webapp/create_group_gathering_rule.html",{
        "rules":rules,
        "cameras":cameras
    })


def toggle_group_rule(request,rule_key):
    r=Rule.objects.get(rule_type="group_gathering")
    rules=r.rules_json
    rules[rule_key]["active"]=not rules[rule_key]["active"]
    r.rules_json=rules
    r.save()
    return redirect("create_group_gathering_rule")


def delete_group_rule(request,rule_key):
    r=Rule.objects.get(rule_type="group_gathering")
    rules=r.rules_json
    del rules[rule_key]
    r.rules_json=rules
    r.save()
    return redirect("create_group_gathering_rule")


#-----------------SAFETY RULE-------------------
def create_helmet_rule(request):
    rule_obj, _ = Rule.objects.get_or_create(
        rule_type="helmet",
        defaults={"rules_json": {}}
    )

    rules = rule_obj.rules_json or {}

    if request.method == "POST":
        rule_key = f"rule_{len(rules)+1}"

        rules[rule_key] = {
            "place": request.POST.getlist("place"),
            "head_email": request.POST.get("head_email"),
            "active": request.POST.get("active") == "true"
        }

        rule_obj.rules_json = rules
        rule_obj.save()
        return redirect("create_helmet_rule")

    cameras = list(streams.keys())

    return render(request, "webapp/create_helmet_rule.html", {
        "rules": rules,
        "cameras": cameras
    })


def toggle_helmet_rule(request, rule_key):
    r = Rule.objects.get(rule_type="helmet")
    rules = r.rules_json or {}

    if rule_key in rules:
        rules[rule_key]["active"] = not rules[rule_key].get("active", False)
        r.rules_json = rules
        r.save()

    return redirect("create_helmet_rule")



def delete_helmet_rule(request, rule_key):
    r = Rule.objects.get(rule_type="helmet")
    rules = r.rules_json or {}

    if rule_key in rules:
        del rules[rule_key]
        r.rules_json = rules
        r.save()

    return redirect("create_helmet_rule")


#--------------Rule dashboard--------------------------
def violation_dashboard(request):
    # Base queryset
    records = EmailSend.objects.exclude(
        rule_category__icontains="meeting"
    ).exclude(
        rule_category__icontains="unknown"
    ).exclude(
        rule_category__icontains="group"
    ).order_by("-created_at")

    # ─── Filters ───
    rule      = request.GET.get("rule_type")
    employee  = request.GET.get("employee")
    date_from = request.GET.get("date_from")
    date_to   = request.GET.get("date_to")

    if rule:
        rule = rule.lower()
        if rule == "restricted":
            records = records.filter(rule_category__icontains="restricted")
        elif rule == "allowed":
            records = records.filter(rule_category__icontains="allowed")
        elif rule in ("inout", "in/out"):
            records = records.filter(rule_category__icontains="inout") | \
                      records.filter(rule_category__icontains="in/out")
        elif rule == "phone":
            records = records.filter(rule_category__icontains="phone")
        elif rule == "safety":
            records = records.filter(rule_category__icontains="safety")

    if employee:
        records = records.filter(
            Q(employee_id__icontains=employee) |
            Q(employee_name__icontains=employee)
        )

    if date_from:
        records = records.filter(created_at__date__gte=date_from)

    if date_to:
        records = records.filter(created_at__date__lte=date_to)

    # ─── Dynamic page size ───
    page_size_str = request.GET.get("page_size", "100")

    try:
        per_page = int(page_size_str)
        # Safety limits
        if per_page < 5:
            per_page = 5
        if per_page > 500:
            per_page = 500
    except (ValueError, TypeError):
        per_page = 100

    # Create paginator with the actual requested size
    paginator = Paginator(records, per_page)

    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(request, "webapp/violation_dashboard.html", {
        "page_obj": page_obj,
        "current_page_size": per_page,   # ← needed for <select> selected=""
    })

def export_violation_csv(request):

    records = EmailSend.objects.exclude(
        rule_category__icontains="meeting"
    ).exclude(
        rule_category__icontains="unknown"
    ).exclude(
        rule_category__icontains="group"
    ).order_by("-created_at")

    rule = request.GET.get("rule_type")
    employee = request.GET.get("employee")
    df = request.GET.get("date_from")
    dt = request.GET.get("date_to")

    if rule:
        if rule == "restricted":
            records = records.filter(rule_category__icontains="Restricted")
        elif rule == "allowed":
            records = records.filter(rule_category__icontains="Allowed")
        elif rule == "inout":
            records = records.filter(rule_category__iexact="InOut Rule")
        elif rule == "phone":
            records = records.filter(rule_category__icontains="Phone")
        elif rule == "safety":
            records = records.filter(rule_category__icontains="Safety")

    if employee:
        records = records.filter(
            Q(employee_id__icontains=employee) |
            Q(employee_name__icontains=employee)
        )

    if df:
        records = records.filter(created_at__date__gte=df)

    if dt:
        records = records.filter(created_at__date__lte=dt)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=violations.csv"

    writer = csv.writer(response)
    writer.writerow([
        "Rule Type",
        "Employee ID",
        "Employee Name",
        "Department",
        "Location",
        "Date & Time"
    ])

    for r in records:
        writer.writerow([
            r.rule_category,
            r.employee_id,
            r.employee_name,
            r.employee_dept,
            r.place,
            r.created_at
        ])

    return response






#-------------- Employee Detail --------------------





def employee_details(request):

    # get page size from request (default 10)
    per_page = request.GET.get("per_page", 10)

    try:
        per_page = int(per_page)
    except:
        per_page = 10

    # base queryset
    employees = Employee.objects.all().order_by("-id")

    # pagination
    paginator = Paginator(employees, per_page)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "webapp/employee_details.html", {
        "page_obj": page_obj,
        "current_page_size": per_page,
    })





 