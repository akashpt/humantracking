from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name="index"),
    path('camera/', views.camera_index, name="camera"),
    path("camera-chart/", views.camera_chart_api, name="camera_chart_api"),
    
    path("face-register/", views.face_register, name="face_register"),
    path("face-record/<int:employee_db_id>/", views.face_record, name="face_record"),
    path("upload-face-video/", views.upload_face_video, name="upload_face_video"),
    
    path("video_feed/<str:name>/", views.video_feed, name="video_feed"),
    path("track/", views.track_employee, name="track_employee"),
    
    path("detected-faces/", views.detected_faces, name="detected_faces"),
    path("no-face/", views.no_face, name="no_face"),
    
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/edit/<int:pk>/", views.employee_edit, name="employee_edit"),
    path("employees/delete/<int:pk>/", views.employee_delete, name="employee_delete"),
    
    path("attendance/", views.attendance_page, name="attendance_page"),
    
    path("login/", views.login_view, name="login"),
    path("rules/create/", views.create_rule, name="create_rule"),
    
    path("rules/meeting/", views.create_meeting_rule, name="create_meeting_rule"),
    path("rules/meeting/toggle/<str:rule_key>/",views.toggle_meeting_rule,name="toggle_meeting_rule"),
    path("rules/meeting/delete/<str:rule_key>/",views.delete_meeting_rule,name="delete_meeting_rule"),
    
    path("rules/allowed-place/",views.create_allowed_place_rule,name="create_allowed_place_rule"),
    path("rules/allowed-place/toggle/<str:rule_key>/",views.toggle_allowed_place_rule,name="toggle_allowed_place_rule"),
    path("rules/allowed-place/delete/<str:rule_key>/",views.delete_allowed_place_rule,name="delete_allowed_place_rule"),

    path("restricted-zone/", views.create_restricted_zone_rule, name="create_restricted_zone_rule"),
    path("restricted-zone/toggle/<str:rule_key>/",views.toggle_restricted_zone_rule,name="toggle_restricted_zone_rule"),
    path("restricted-zone/delete/<str:rule_key>/",views.delete_restricted_zone_rule,name="delete_restricted_zone_rule"),

    path("rules/inout-time/",views.create_inout_time_rule,name="create_inout_time_rule"),
    path("rules/inout-time/toggle/<str:rule_key>/",views.toggle_inout_time_rule,name="toggle_inout_time_rule"),
    path("rules/inout-time/delete/<str:rule_key>/",views.delete_inout_time_rule,name="delete_inout_time_rule"),
     
    path("rules/unknown-alert/",views.create_unknown_alert_rule,name="create_unknown_alert_rule"),
    path("rules/unknown-alert/toggle/",views.toggle_unknown_alert_rule,name="toggle_unknown_alert_rule"),
    path("rules/unknown-alert/delete/",views.delete_unknown_alert_rule,name="delete_unknown_alert_rule"),
    
    path("rules/phone-usage/",views.create_phone_usage_rule, name="create_phone_usage_rule"),
    path("rules/phone-usage/toggle/<str:rule_key>/",views.toggle_phone_usage_rule,name="toggle_phone_usage_rule"),
    path("rules/phone-usage/delete/<str:rule_key>/",views.delete_phone_usage_rule,name="delete_phone_usage_rule"),

    path("rules/group-gathering/",views.create_group_gathering_rule,name="create_group_gathering_rule"),
    path("rules/group-gathering/toggle/<str:rule_key>/",views.toggle_group_rule,name="toggle_group_rule"),
    path("rules/group-gathering/delete/<str:rule_key>/",views.delete_group_rule,name="delete_group_rule"),
    
    path("rules/helmet/", views.create_helmet_rule, name="create_helmet_rule"),
    path("rules/helmet/toggle/<str:rule_key>/", views.toggle_helmet_rule, name="toggle_helmet_rule"),
    path("rules/helmet/delete/<str:rule_key>/", views.delete_helmet_rule, name="delete_helmet_rule"),

    path("violation-dashboard/",views.violation_dashboard,name="violation_dashboard"),
    path("export-csv/", views.export_violation_csv, name="export_violation_csv"),
    
    path("employee_details/",views.employee_details,name="employee_details"),
    

]
