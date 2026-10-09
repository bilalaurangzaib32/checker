import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime

from config import load_config, save_config
from ssh_client import SSHMonitorClient
from website_monitor import check_all_websites
from discord_notifier import DiscordNotifier

class MonitoringEngine:
    def __init__(self):
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Cached latest data
        self.latest_status: Dict[str, Any] = {
            "last_check_time": None,
            "vps_online": False,
            "vps_error": None,
            "system": {},
            "docker": {"available": False, "containers": [], "summary": {}},
            "websites": [],
            "security": {},
            "active_alerts": []
        }

        # Historical metrics for UI charts (up to 30 points)
        self.history: List[Dict[str, Any]] = []
        self.max_history = 40

        # State tracking for alerts debouncing
        self.prev_website_states: Dict[str, bool] = {} # url -> online
        self.prev_container_states: Dict[str, str] = {} # container_name -> state
        self.cpu_alerted = False
        self.ram_alerted = False
        self.disk_alerted = False
        self.recent_incidents: List[Dict[str, Any]] = []

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("Monitoring Engine started in background.")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=3)
        print("Monitoring Engine stopped.")

    def _run_loop(self):
        # Run immediate first check
        self.run_single_check()

        while self.running:
            config = load_config()
            interval = max(15, config.get("monitor_interval_seconds", 60))

            # Sleep in small slices so stopping is immediate
            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

            if not self.running:
                break

            try:
                self.run_single_check()
            except Exception as e:
                print(f"Error in monitor loop run_single_check: {e}")

    def run_single_check(self) -> Dict[str, Any]:
        config = load_config()
        vps_cfg = config.get("vps", {})
        discord_cfg = config.get("discord", {})
        thresholds = config.get("thresholds", {})
        websites_list = config.get("websites", [])

        notifier = DiscordNotifier(discord_cfg.get("webhook_url", ""))
        vps_ip = vps_cfg.get("host", "").strip()

        # 1. Collect VPS Metrics if enabled & host present
        vps_data = {
            "online": False,
            "error": "VPS Host not configured" if not vps_ip else None,
            "system": {
                "cpu_percent": 0.0,
                "ram_percent": 0.0,
                "ram_total_mb": 0,
                "ram_used_mb": 0,
                "disk_percent": 0.0,
                "disk_total_gb": 0.0,
                "disk_used_gb": 0.0,
                "uptime_str": "-",
                "load_avg": [0, 0, 0]
            },
            "docker": {"available": False, "containers": [], "summary": {"total": 0, "running": 0, "stopped": 0, "restarting": 0}},
            "security": {"failed_logins_count": 0, "recent_failed_ips": []}
        }

        if vps_cfg.get("enabled", True) and vps_ip:
            ssh_client = SSHMonitorClient(
                host=vps_ip,
                port=vps_cfg.get("port", 22),
                username=vps_cfg.get("username", "root"),
                password=vps_cfg.get("password", ""),
                private_key_str=vps_cfg.get("private_key", "")
            )
            vps_data = ssh_client.collect_all_metrics()

        # 2. Check Websites
        websites_data = []
        if websites_list:
            websites_data = check_all_websites(websites_list)

        # 3. Process Alerts & Health Status
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        active_alerts = []

        # --- Check VPS Availability ---
        if vps_ip and not vps_data.get("online"):
            msg = f"VPS `{vps_ip}` is UNREACHABLE: {vps_data.get('error')}"
            active_alerts.append(msg)
            self._log_incident("CRITICAL", "VPS Connection Failure", msg)

        # --- Check System Thresholds ---
        sys_m = vps_data.get("system", {})
        cpu = sys_m.get("cpu_percent", 0.0)
        ram = sys_m.get("ram_percent", 0.0)
        disk = sys_m.get("disk_percent", 0.0)

        cpu_limit = thresholds.get("cpu_percent", 85.0)
        ram_limit = thresholds.get("ram_percent", 90.0)
        disk_limit = thresholds.get("disk_percent", 90.0)

        unusual_issues = []

        # CPU Check
        if cpu >= cpu_limit:
            issue = f"High CPU Usage: **{cpu}%** (Threshold: {cpu_limit}%)"
            unusual_issues.append(issue)
            active_alerts.append(issue)
            if not self.cpu_alerted:
                self.cpu_alerted = True
                self._log_incident("WARNING", "High CPU Load", issue)
                if discord_cfg.get("enabled", True):
                    notifier.send_incident_alert("High CPU Utilization", [issue], vps_ip, severity="warning")
        else:
            if self.cpu_alerted and discord_cfg.get("alert_on_recovery", True):
                self.cpu_alerted = False
                self._log_incident("RESOLVED", "CPU Normalized", f"CPU dropped to {cpu}%")
                notifier.send_recovery_alert("CPU Normalized", f"CPU load has returned to normal: **{cpu}%**", vps_ip)

        # RAM Check
        if ram >= ram_limit:
            issue = f"High RAM Usage: **{ram}%** (Threshold: {ram_limit}%)"
            unusual_issues.append(issue)
            active_alerts.append(issue)
            if not self.ram_alerted:
                self.ram_alerted = True
                self._log_incident("WARNING", "High Memory Usage", issue)
                if discord_cfg.get("enabled", True):
                    notifier.send_incident_alert("High Memory Utilization", [issue], vps_ip, severity="warning")
        else:
            if self.ram_alerted and discord_cfg.get("alert_on_recovery", True):
                self.ram_alerted = False
                self._log_incident("RESOLVED", "Memory Normalized", f"Memory usage dropped to {ram}%")
                notifier.send_recovery_alert("Memory Normalized", f"RAM usage has returned to normal: **{ram}%**", vps_ip)

        # Disk Check
        if disk >= disk_limit:
            issue = f"Disk Space Critical: **{disk}%** full (Threshold: {disk_limit}%)"
            unusual_issues.append(issue)
            active_alerts.append(issue)
            if not self.disk_alerted:
                self.disk_alerted = True
                self._log_incident("CRITICAL", "Disk Near Capacity", issue)
                if discord_cfg.get("enabled", True):
                    notifier.send_incident_alert("Disk Space Critical", [issue], vps_ip, severity="critical")
        else:
            if self.disk_alerted:
                self.disk_alerted = False

        # --- Check Docker Containers ---
        docker_data = vps_data.get("docker", {})
        for container in docker_data.get("containers", []):
            c_name = container.get("name", "Unknown")
            c_state = container.get("state", "").lower()
            prev_state = self.prev_container_states.get(c_name)

            if c_state != "running":
                active_alerts.append(f"Docker container `{c_name}` is {c_state.upper()} ({container.get('status')})")
                if prev_state == "running" or prev_state is None:
                    # New failure transition
                    issue = f"Container `{c_name}` transitioned to `{c_state}` ({container.get('status')})"
                    self._log_incident("CRITICAL", "Docker Container Stopped/Failed", issue)
                    if discord_cfg.get("enabled", True):
                        notifier.send_incident_alert("Docker Container Down", [issue], vps_ip, severity="critical")
            else:
                if prev_state and prev_state != "running":
                    # Recovery transition
                    msg = f"Docker container `{c_name}` is back **RUNNING**."
                    self._log_incident("RESOLVED", "Container Restored", msg)
                    if discord_cfg.get("alert_on_recovery", True):
                        notifier.send_recovery_alert("Container Restored", msg, vps_ip)

            self.prev_container_states[c_name] = c_state

        # --- Check Websites ---
        for site in websites_data:
            s_url = site.get("url")
            s_online = site.get("online")
            s_name = site.get("name", s_url)
            prev_online = self.prev_website_states.get(s_url)

            if not s_online:
                active_alerts.append(f"Website `{s_name}` DOWN: {site.get('error')}")
                if prev_online is True or prev_online is None:
                    issue = f"Website `{s_name}` ({s_url}) is UNREACHABLE: {site.get('error')}"
                    self._log_incident("CRITICAL", "Website Offline", issue)
                    if discord_cfg.get("enabled", True):
                        notifier.send_incident_alert("Website Offline Alert", [issue], vps_ip, severity="critical")
            else:
                if prev_online is False:
                    # Recovered
                    msg = f"Website `{s_name}` ({s_url}) is back ONLINE (Status {site.get('status_code')}, Latency {site.get('latency_ms')}ms)."
                    self._log_incident("RESOLVED", "Website Restored", msg)
                    if discord_cfg.get("alert_on_recovery", True):
                        notifier.send_recovery_alert("Website Back Online", msg, vps_ip)

            self.prev_website_states[s_url] = s_online

        # --- Check Security (Failed SSH logins spike) ---
        sec = vps_data.get("security", {})
        failed_ssh = sec.get("failed_logins_count", 0)
        failed_limit = thresholds.get("failed_ssh_attempts", 5)
        if failed_ssh >= failed_limit:
            ips = ", ".join(sec.get("recent_failed_ips", [])) or "multiple"
            sec_issue = f"Possible SSH Brute-Force Attack: **{failed_ssh} failed login attempts** (Attacker IPs: {ips})"
            active_alerts.append(sec_issue)
            self._log_incident("WARNING", "SSH Brute-Force Activity", sec_issue)

        # 4. Check Periodic 6-Hour Report
        last_report_ts = config.get("last_report_timestamp", 0)
        report_interval_hrs = discord_cfg.get("report_interval_hours", 6)
        report_interval_secs = report_interval_hrs * 3600
        now_ts = time.time()

        if discord_cfg.get("enabled", True) and (now_ts - last_report_ts >= report_interval_secs):
            print("Sending 6-hour periodic Discord report...")
            sent = notifier.send_periodic_report(
                vps_ip=vps_ip,
                sys_metrics=sys_m,
                docker_data=docker_data,
                websites_data=websites_data,
                security_data=sec,
                hours_interval=report_interval_hrs
            )
            if sent:
                config["last_report_timestamp"] = now_ts
                save_config(config)

        # 5. Update In-Memory Cache and Charts
        with self._lock:
            self.latest_status = {
                "last_check_time": current_time_str,
                "vps_online": vps_data.get("online", False),
                "vps_error": vps_data.get("error"),
                "system": sys_m,
                "docker": docker_data,
                "websites": websites_data,
                "security": sec,
                "active_alerts": active_alerts
            }

            # Chart history point
            time_label = datetime.now().strftime("%H:%M:%S")
            self.history.append({
                "time": time_label,
                "cpu": cpu,
                "ram": ram,
                "disk": disk
            })
            if len(self.history) > self.max_history:
                self.history.pop(0)

        return self.latest_status

    def _log_incident(self, level: str, title: str, details: str):
        with self._lock:
            self.recent_incidents.insert(0, {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": level,
                "title": title,
                "details": details
            })
            if len(self.recent_incidents) > 50:
                self.recent_incidents.pop()

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": self.latest_status,
                "history": list(self.history),
                "incidents": list(self.recent_incidents)
            }

    def force_send_report(self) -> Dict[str, Any]:
        config = load_config()
        discord_cfg = config.get("discord", {})
        notifier = DiscordNotifier(discord_cfg.get("webhook_url", ""))
        if not notifier.is_configured():
            return {"success": False, "message": "Discord Webhook is not configured."}

        snapshot = self.get_snapshot()["status"]
        sent = notifier.send_periodic_report(
            vps_ip=config.get("vps", {}).get("host", ""),
            sys_metrics=snapshot.get("system", {}),
            docker_data=snapshot.get("docker", {}),
            websites_data=snapshot.get("websites", []),
            security_data=snapshot.get("security", {}),
            hours_interval=discord_cfg.get("report_interval_hours", 6)
        )
        if sent:
            config["last_report_timestamp"] = time.time()
            save_config(config)
            return {"success": True, "message": "6-Hour Report sent to Discord successfully!"}
        return {"success": False, "message": "Failed to deliver report to Discord. Verify webhook URL."}

# Global Engine instance
engine = MonitoringEngine()
