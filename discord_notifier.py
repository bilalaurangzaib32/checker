import datetime
import json
from typing import Dict, Any, List, Optional
import requests

# Discord Colors (hex converted to decimal)
COLOR_CRITICAL = 0xE74C3C  # Red
COLOR_WARNING  = 0xE67E22  # Orange
COLOR_SUCCESS  = 0x2ECC71  # Green
COLOR_INFO     = 0x3498DB  # Blue

class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url.strip() if webhook_url else ""

    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.webhook_url.startswith("https://discord.com/api/webhooks/"))

    def send_webhook(self, payload: Dict[str, Any]) -> bool:
        if not self.is_configured():
            return False
        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Error sending Discord webhook: {e}")
            return False

    def send_test_message(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "message": "Discord Webhook URL is invalid or not configured."}
        
        embed = {
            "title": "🔔 VPS-Sentinel Test Notification",
            "description": "Discord Webhook connection is working perfectly! You will receive 6-hour reports and instant alerts here.",
            "color": COLOR_SUCCESS,
            "fields": [
                {"name": "Status", "value": "🟢 Connected", "inline": True},
                {"name": "Timestamp", "value": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": True}
            ],
            "footer": {"text": "VPS-Sentinel 24/7 Monitor"}
        }
        ok = self.send_webhook({"embeds": [embed]})
        if ok:
            return {"success": True, "message": "Test notification delivered to Discord successfully!"}
        return {"success": False, "message": "Failed to send message to Discord. Check your Webhook URL."}

    def send_incident_alert(self, title: str, issues: List[str], server_ip: str, severity: str = "critical") -> bool:
        """Sends instant notification for unusual activities (crash, spike, down, security attack)."""
        if not self.is_configured() or not issues:
            return False

        color = COLOR_CRITICAL if severity == "critical" else COLOR_WARNING
        icon = "🚨" if severity == "critical" else "⚠️"

        issue_text = "\n".join([f"• {issue}" for issue in issues])

        embed = {
            "title": f"{icon} [UNUSUAL ACTIVITY DETECTED] {title}",
            "description": f"**Server Target:** `{server_ip}`\n\n**Detected Issues:**\n{issue_text}",
            "color": color,
            "fields": [
                {"name": "Severity", "value": f"**{severity.upper()}**", "inline": True},
                {"name": "Detected At", "value": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
            ],
            "footer": {"text": "VPS-Sentinel Incident Detection Engine"}
        }

        return self.send_webhook({"content": f"@here Alert on server `{server_ip}`" if severity == "critical" else "", "embeds": [embed]})

    def send_recovery_alert(self, title: str, details: str, server_ip: str) -> bool:
        """Sends notification when an issue is resolved/recovered."""
        if not self.is_configured():
            return False

        embed = {
            "title": f"✅ [RECOVERED] {title}",
            "description": f"**Server Target:** `{server_ip}`\n\n{details}",
            "color": COLOR_SUCCESS,
            "fields": [
                {"name": "Status", "value": "🟢 Normal / Healthy", "inline": True},
                {"name": "Resolved At", "value": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
            ],
            "footer": {"text": "VPS-Sentinel Auto Recovery"}
        }
        return self.send_webhook({"embeds": [embed]})

    def send_periodic_report(self, vps_ip: str, sys_metrics: Dict[str, Any],
                             docker_data: Dict[str, Any], websites_data: List[Dict[str, Any]],
                             security_data: Dict[str, Any], hours_interval: int = 6) -> bool:
        """Sends rich 6-hour periodic health and analytics summary to Discord."""
        if not self.is_configured():
            return False

        cpu = sys_metrics.get("cpu_percent", 0.0)
        ram = sys_metrics.get("ram_percent", 0.0)
        ram_used = sys_metrics.get("ram_used_mb", 0)
        ram_total = sys_metrics.get("ram_total_mb", 0)
        disk = sys_metrics.get("disk_percent", 0.0)
        disk_used = sys_metrics.get("disk_used_gb", 0.0)
        disk_total = sys_metrics.get("disk_total_gb", 0.0)
        uptime = sys_metrics.get("uptime_str", "Unknown")

        # Docker summary
        dock_sum = docker_data.get("summary", {})
        d_total = dock_sum.get("total", 0)
        d_running = dock_sum.get("running", 0)
        d_stopped = dock_sum.get("stopped", 0)
        d_restarting = dock_sum.get("restarting", 0)

        # Websites summary
        w_total = len(websites_data)
        w_online = sum(1 for w in websites_data if w.get("online"))
        w_offline = w_total - w_online

        # Failed logins
        failed_logins = security_data.get("failed_logins_count", 0)

        # Overall Status determine
        is_healthy = True
        warnings = []
        if cpu > 80:
            is_healthy = False
            warnings.append(f"High CPU: {cpu}%")
        if ram > 85:
            is_healthy = False
            warnings.append(f"High RAM: {ram}%")
        if disk > 85:
            is_healthy = False
            warnings.append(f"High Disk: {disk}%")
        if d_stopped > 0 or d_restarting > 0:
            warnings.append(f"{d_stopped + d_restarting} Docker containers inactive")
        if w_offline > 0:
            is_healthy = False
            warnings.append(f"{w_offline} website(s) unreachable")

        overall_badge = "🟢 ALL SYSTEMS HEALTHY" if is_healthy and not warnings else ("🟡 WARNINGS DETECTED" if is_healthy else "🔴 ATTENTION REQUIRED")
        color = COLOR_SUCCESS if is_healthy and not warnings else (COLOR_WARNING if is_healthy else COLOR_CRITICAL)

        # Containers details list
        containers_snippet = ""
        c_list = docker_data.get("containers", [])
        if c_list:
            c_lines = []
            for c in c_list[:8]: # top 8
                st_icon = "🟢" if c.get("state") == "running" else "🔴"
                c_lines.append(f"{st_icon} **{c.get('name')}** (`{c.get('cpu_usage', '0%')}` CPU, `{c.get('mem_percent', '0%')}` RAM)")
            containers_snippet = "\n".join(c_lines)
            if len(c_list) > 8:
                containers_snippet += f"\n*...and {len(c_list)-8} more containers*"
        else:
            containers_snippet = "*No active Docker containers detected.*"

        # Websites details snippet
        websites_snippet = ""
        if websites_data:
            w_lines = []
            for w in websites_data[:6]:
                w_icon = "🟢" if w.get("online") else "🔴"
                w_lines.append(f"{w_icon} **{w.get('name')}**: `{w.get('status_code')}` ({w.get('latency_ms')}ms)")
            websites_snippet = "\n".join(w_lines)
        else:
            websites_snippet = "*No websites configured.*"

        embed = {
            "title": f"📊 VPS-Sentinel: {hours_interval}-Hour Health & Analytics Report",
            "description": f"**VPS IP:** `{vps_ip or 'Not Set'}`\n**Overall Health:** **{overall_badge}**\n**System Uptime:** {uptime}",
            "color": color,
            "fields": [
                {
                    "name": "🖥️ Server Resources",
                    "value": f"• **CPU Load:** `{cpu}%`\n• **Memory:** `{ram}%` ({ram_used}MB / {ram_total}MB)\n• **Disk Storage:** `{disk}%` ({disk_used}GB / {disk_total}GB)",
                    "inline": False
                },
                {
                    "name": f"🐳 Docker Containers ({d_running}/{d_total} Running)",
                    "value": containers_snippet,
                    "inline": False
                },
                {
                    "name": f"🌐 Websites & Endpoints ({w_online}/{w_total} Online)",
                    "value": websites_snippet,
                    "inline": False
                },
                {
                    "name": "🛡️ Security Snapshot",
                    "value": f"• **Recent Failed SSH Logins:** `{failed_logins}`",
                    "inline": True
                },
                {
                    "name": "⏰ Next Scheduled Report",
                    "value": f"In **{hours_interval} Hours**",
                    "inline": True
                }
            ],
            "footer": {
                "text": f"VPS-Sentinel Automated Report • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            }
        }

        return self.send_webhook({"embeds": [embed]})
