from django.apps import AppConfig
import os
import threading
import time
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)


class WebappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'webapp'

    def ready(self):
        # ❌ prevent camera start during makemigrations/migrate
        if os.environ.get("RUN_MAIN") != "true":
            return

        from webapp.capture import CameraWorker
        from webapp import views
        import atexit
        from webapp.rule_executor import execute_meeting_rules,execute_allowed_place_rules,execute_restricted_zone_rules,execute_inout_time_rules,execute_unknown_alert_rule,execute_phone_usage_rules,execute_group_gathering_rules,execute_helmet_rules


        CAMERA_URLS = {
            #"webcam": 0,                         
            #"Entry door": "rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/101", 
            #"Lunch Hall": "rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/201",
            #"Cabin_1": "rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/301",
            #"Working Hall 1": "rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/401",
            # "Working Hall 2": "rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/501",
            #"Admin cabin":"rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/601",
            #"Conference Hall": "rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/701",
            #"Washroom"  : "rtsp://admin:Texa@321@192.168.1.2:554/Streaming/Channels/801" 
         }
        views.streams = {
            name: CameraWorker(name, url)
            for name, url in CAMERA_URLS.items()
        }
        # ================= RULE EXECUTOR =================
        def rule_worker():
            while True:
                try:
                    execute_meeting_rules()
                    execute_allowed_place_rules()
                    execute_restricted_zone_rules() 
                    execute_inout_time_rules()
                    execute_unknown_alert_rule()
                    execute_phone_usage_rules()
                    execute_group_gathering_rules()
                    execute_helmet_rules()
                except Exception as e:
                    print("❌ Rule executor error:", e)
                time.sleep(60)   # check every 1 minute

        threading.Thread(
            target=rule_worker,
            daemon=True
        ).start()
        
        atexit.register(lambda: [c.stop() for c in views.streams.values()])


