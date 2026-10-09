import io
import json
import re
import socket
import time
from typing import Dict, Any, List, Optional, Tuple
import paramiko

class SSHMonitorClient:
    def __init__(self, host: str, port: int = 22, username: str = "root",
                 password: str = "", private_key_str: str = "", timeout: int = 10):
        self.host = host.strip()
        self.port = int(port) if port else 22
        self.username = username.strip() or "root"
        self.password = password
        self.private_key_str = private_key_str.strip()
        self.timeout = timeout

    def _get_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": self.timeout,
            "banner_timeout": 15,
            "auth_timeout": 15
        }

        if self.private_key_str:
            # Try parsing private key (Ed25519, RSA, ECDSA)
            key_file = io.StringIO(self.private_key_str)
            pkey = None
            for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                try:
                    key_file.seek(0)
                    pkey = key_cls.from_private_key(key_file, password=self.password if self.password else None)
                    break
                except Exception:
                    continue
            if pkey:
                connect_kwargs["pkey"] = pkey
            else:
                # Fallback to password
                if self.password:
                    connect_kwargs["password"] = self.password
        elif self.password:
            connect_kwargs["password"] = self.password

        client.connect(**connect_kwargs)
        return client

    def execute_command(self, cmd: str, timeout: int = 12) -> Tuple[bool, str, str]:
        """Executes a command and returns (success, stdout, stderr)"""
        client = None
        try:
            client = self._get_client()
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return True, out, err
        except Exception as e:
            return False, "", str(e)
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    def check_network_reachability(self, ports: Optional[List[int]] = None) -> Dict[str, Any]:
        """Probes host via TCP to test reachability and latency without SSH login credentials."""
        if not ports:
            ports = [self.port, 80, 443]

        open_ports = []
        overall_latency = None
        is_reachable = False
        port_names = {22: "SSH", 80: "HTTP", 443: "HTTPS", 8080: "HTTP-Alt", 8443: "HTTPS-Alt", 3000: "App", 9000: "Portainer"}

        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(min(self.timeout, 3.5))
            t0 = time.perf_counter()
            try:
                ret = s.connect_ex((self.host, p))
                lat = round((time.perf_counter() - t0) * 1000)
                is_open = (ret == 0)
                if is_open:
                    is_reachable = True
                    if overall_latency is None or lat < overall_latency:
                        overall_latency = lat
                open_ports.append({
                    "port": p,
                    "name": port_names.get(p, f"Port {p}"),
                    "open": is_open,
                    "latency_ms": lat if is_open else None
                })
            except Exception:
                open_ports.append({
                    "port": p,
                    "name": port_names.get(p, f"Port {p}"),
                    "open": False,
                    "latency_ms": None
                })
            finally:
                s.close()

        return {
            "reachable": is_reachable,
            "latency_ms": overall_latency or 0,
            "ports": open_ports
        }

    def test_connection(self) -> Dict[str, Any]:
        """Tests SSH reachability or TCP reachability."""
        if not self.host:
            return {"success": False, "message": "Host IP not specified."}

        # If credentials provided, test SSH command execution
        if self.password or self.private_key_str:
            try:
                ok, out, err = self.execute_command("uname -a", timeout=7)
                if ok:
                    return {"success": True, "message": f"Connected successfully via SSH! OS: {out}"}
                else:
                    net = self.check_network_reachability()
                    if net["reachable"]:
                        return {"success": False, "message": f"Host is online (Port open, latency {net['latency_ms']}ms), but SSH auth failed: {err}"}
                    return {"success": False, "message": f"Connection failed: {err}"}
            except Exception as e:
                return {"success": False, "message": f"SSH Error: {str(e)}"}

        # Agentless IP Mode (No credentials provided)
        net = self.check_network_reachability()
        if net["reachable"]:
            active = [f"{p['port']}/{p['name']} ({p['latency_ms']}ms)" for p in net["ports"] if p["open"]]
            return {
                "success": True,
                "message": f"Host {self.host} is ONLINE! Open ports: {', '.join(active)} (Agentless Mode)"
            }
        else:
            return {
                "success": False,
                "message": f"Host {self.host} is unreachable or timing out on ports 22, 80, 443."
            }

    def collect_all_metrics(self) -> Dict[str, Any]:
        """Collects system metrics, docker status, and security alerts in a single composite pass."""
        result: Dict[str, Any] = {
            "online": False,
            "error": None,
            "system": {},
            "docker": {"available": False, "containers": [], "summary": {}},
            "security": {"failed_logins_count": 0, "recent_failed_ips": []}
        }

        if not self.host:
            result["error"] = "VPS IP is not configured."
            return result

        # Agentless IP Mode if credentials are not provided
        if not self.password and not self.private_key_str:
            net = self.check_network_reachability()
            if net["reachable"]:
                open_ports_str = ", ".join([f"{p['port']}/{p['name']}" for p in net["ports"] if p["open"]])
                result["online"] = True
                result["mode"] = "network_probe"
                result["latency_ms"] = net["latency_ms"]
                result["open_ports"] = net["ports"]
                result["system"] = {
                    "cpu_percent": 0.0,
                    "ram_percent": 0.0,
                    "ram_total_mb": 0,
                    "ram_used_mb": 0,
                    "disk_percent": 0.0,
                    "disk_total_gb": 0.0,
                    "disk_used_gb": 0.0,
                    "uptime_str": f"Online (TCP {net['latency_ms']}ms)",
                    "load_avg": [0, 0, 0],
                    "latency_ms": net["latency_ms"],
                    "ports_summary": open_ports_str,
                    "agentless": True
                }
                result["docker"] = {
                    "available": False,
                    "containers": [],
                    "summary": {"total": 0, "running": 0, "stopped": 0, "restarting": 0},
                    "note": "IP-only Mode: Reachability and Ports monitored."
                }
                result["security"] = {
                    "failed_logins_count": 0,
                    "recent_failed_ips": [],
                    "note": "IP-only Mode"
                }
                return result
            else:
                result["online"] = False
                result["error"] = f"Host {self.host} is unreachable via TCP network probes."
                return result

        client = None
        try:
            client = self._get_client()
            result["online"] = True
        except Exception as e:
            # Fallback reachability check
            net = self.check_network_reachability()
            if net["reachable"]:
                result["online"] = True
                result["mode"] = "network_probe"
                result["latency_ms"] = net["latency_ms"]
                result["open_ports"] = net["ports"]
                result["system"] = {
                    "cpu_percent": 0.0,
                    "ram_percent": 0.0,
                    "ram_total_mb": 0,
                    "ram_used_mb": 0,
                    "disk_percent": 0.0,
                    "disk_total_gb": 0.0,
                    "disk_used_gb": 0.0,
                    "uptime_str": f"Online (TCP {net['latency_ms']}ms)",
                    "load_avg": [0, 0, 0],
                    "latency_ms": net["latency_ms"],
                    "agentless": True
                }
                result["docker"] = {"available": False, "containers": [], "summary": {}}
                result["security"] = {"failed_logins_count": 0, "recent_failed_ips": []}
                return result

            result["error"] = f"Unable to connect to VPS ({self.host}): {str(e)}"
            return result

        try:
            # 1. System Metrics Commands
            # Run composite system script to fetch CPU, RAM, Disk, Uptime, LoadAvg in one SSH roundtrip
            composite_sys_cmd = r"""
echo "===UPTIME==="
cat /proc/uptime 2>/dev/null || uptime
echo "===MEM==="
cat /proc/meminfo 2>/dev/null || free -m
echo "===CPU==="
cat /proc/stat | grep '^cpu '
sleep 0.5
cat /proc/stat | grep '^cpu '
echo "===DISK==="
df -Pk /
echo "===LOADAVG==="
cat /proc/loadavg 2>/dev/null
"""
            _, sys_out, _ = self._exec_raw(client, composite_sys_cmd)
            result["system"] = self._parse_system_output(sys_out)

            # 2. Docker Containers & Stats
            docker_cmd = r"""
if command -v docker >/dev/null 2>&1; then
    echo "===DOCKER_PS==="
    docker ps -a --no-trunc --format '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","state":"{{.State}}","ports":"{{.Ports}}"}'
    echo "===DOCKER_STATS==="
    docker stats --no-stream --format '{"name":"{{.Name}}","cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}","mem_perc":"{{.MemPerc}}"}' 2>/dev/null
else
    echo "===DOCKER_NONE==="
fi
"""
            _, dock_out, _ = self._exec_raw(client, docker_cmd)
            result["docker"] = self._parse_docker_output(dock_out)

            # 3. Security (Failed SSH logins)
            sec_cmd = r"""
if [ -f /var/log/auth.log ]; then
    grep -i "Failed password" /var/log/auth.log 2>/dev/null | tail -n 25
elif command -v journalctl >/dev/null 2>&1; then
    journalctl -u ssh -u sshd -n 25 --no-pager 2>/dev/null | grep -i "Failed password"
fi
"""
            _, sec_out, _ = self._exec_raw(client, sec_cmd)
            result["security"] = self._parse_security_output(sec_out)

        except Exception as e:
            result["error"] = f"Error during metrics gathering: {str(e)}"
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

        return result

    def _exec_raw(self, client: paramiko.SSHClient, cmd: str, timeout: int = 15) -> Tuple[bool, str, str]:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return True, out, err

    def _parse_system_output(self, raw: str) -> Dict[str, Any]:
        data = {
            "cpu_percent": 0.0,
            "ram_percent": 0.0,
            "ram_total_mb": 0,
            "ram_used_mb": 0,
            "disk_percent": 0.0,
            "disk_total_gb": 0.0,
            "disk_used_gb": 0.0,
            "uptime_str": "Unknown",
            "load_avg": [0.0, 0.0, 0.0]
        }

        parts = raw.split("===")
        sections = {}
        for i in range(1, len(parts), 2):
            sec_name = parts[i].strip()
            sec_content = parts[i+1].strip() if i+1 < len(parts) else ""
            sections[sec_name] = sec_content

        # 1. Parse CPU from 2 consecutive /proc/stat readings
        if "CPU" in sections:
            lines = sections["CPU"].strip().split("\n")
            if len(lines) >= 2:
                try:
                    def parse_cpu_line(l):
                        fields = [float(x) for x in l.strip().split()[1:]]
                        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
                        total = sum(fields)
                        return idle, total

                    idle1, total1 = parse_cpu_line(lines[0])
                    idle2, total2 = parse_cpu_line(lines[1])
                    idle_delta = idle2 - idle1
                    total_delta = total2 - total1
                    if total_delta > 0:
                        cpu_usage = 100.0 * (1.0 - (idle_delta / total_delta))
                        data["cpu_percent"] = round(max(0.0, min(100.0, cpu_usage)), 1)
                except Exception:
                    pass

        # 2. Parse RAM from /proc/meminfo
        if "MEM" in sections:
            mem_text = sections["MEM"]
            mem_total_kb = 0
            mem_avail_kb = 0
            mem_free_kb = 0
            for line in mem_text.splitlines():
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail_kb = int(line.split()[1])
                elif line.startswith("MemFree:"):
                    mem_free_kb = int(line.split()[1])

            if mem_total_kb > 0:
                avail_kb = mem_avail_kb if mem_avail_kb > 0 else mem_free_kb
                used_kb = mem_total_kb - avail_kb
                data["ram_total_mb"] = round(mem_total_kb / 1024)
                data["ram_used_mb"] = round(used_kb / 1024)
                data["ram_percent"] = round((used_kb / mem_total_kb) * 100, 1)

        # 3. Parse Disk (df -Pk /)
        if "DISK" in sections:
            lines = sections["DISK"].strip().splitlines()
            if len(lines) >= 2:
                # format: Filesystem 1024-blocks Used Available Capacity Mounted on
                cols = lines[1].split()
                if len(cols) >= 5:
                    try:
                        total_kb = float(cols[1])
                        used_kb = float(cols[2])
                        perc_str = cols[4].replace("%", "")
                        data["disk_total_gb"] = round(total_kb / (1024 * 1024), 1)
                        data["disk_used_gb"] = round(used_kb / (1024 * 1024), 1)
                        data["disk_percent"] = float(perc_str)
                    except Exception:
                        pass

        # 4. Parse Uptime
        if "UPTIME" in sections:
            line = sections["UPTIME"].strip().splitlines()
            if line:
                try:
                    # /proc/uptime has seconds
                    secs = float(line[0].split()[0])
                    days = int(secs // 86400)
                    hours = int((secs % 86400) // 3600)
                    mins = int((secs % 3600) // 60)
                    parts_up = []
                    if days > 0:
                        parts_up.append(f"{days}d")
                    if hours > 0 or days > 0:
                        parts_up.append(f"{hours}h")
                    parts_up.append(f"{mins}m")
                    data["uptime_str"] = " ".join(parts_up)
                except Exception:
                    data["uptime_str"] = line[0]

        # 5. Parse Load Average
        if "LOADAVG" in sections:
            line = sections["LOADAVG"].strip()
            cols = line.split()
            if len(cols) >= 3:
                try:
                    data["load_avg"] = [float(cols[0]), float(cols[1]), float(cols[2])]
                except Exception:
                    pass

        return data

    def _parse_docker_output(self, raw: str) -> Dict[str, Any]:
        result = {
            "available": False,
            "containers": [],
            "summary": {"total": 0, "running": 0, "stopped": 0, "restarting": 0}
        }

        if "===DOCKER_NONE===" in raw:
            return result

        result["available"] = True
        stats_map = {}

        if "===DOCKER_STATS===" in raw:
            parts = raw.split("===DOCKER_STATS===")
            ps_part = parts[0]
            stats_part = parts[1] if len(parts) > 1 else ""

            for line in stats_part.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    st = json.loads(line)
                    c_name = st.get("name", "").strip()
                    if c_name:
                        stats_map[c_name] = {
                            "cpu": st.get("cpu", "0%"),
                            "mem": st.get("mem", "0B"),
                            "mem_perc": st.get("mem_perc", "0%")
                        }
                except Exception:
                    continue
        else:
            ps_part = raw

        # Parse docker ps
        if "===DOCKER_PS===" in ps_part:
            ps_part = ps_part.split("===DOCKER_PS===")[-1]

        containers = []
        for line in ps_part.strip().splitlines():
            if not line.strip():
                continue
            try:
                c = json.loads(line)
                name = c.get("name", "")
                state = c.get("state", "").lower() # running, exited, restarting, paused

                st = stats_map.get(name, {"cpu": "0%", "mem": "-", "mem_perc": "0%"})
                c["cpu_usage"] = st["cpu"]
                c["mem_usage"] = st["mem"]
                c["mem_percent"] = st["mem_perc"]

                containers.append(c)
                result["summary"]["total"] += 1
                if state == "running":
                    result["summary"]["running"] += 1
                elif "restart" in state:
                    result["summary"]["restarting"] += 1
                else:
                    result["summary"]["stopped"] += 1
            except Exception:
                continue

        result["containers"] = containers
        return result

    def _parse_security_output(self, raw: str) -> Dict[str, Any]:
        failed_count = 0
        ips = []
        ip_regex = re.compile(r'from\s+([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})')
        for line in raw.strip().splitlines():
            if "Failed password" in line:
                failed_count += 1
                match = ip_regex.search(line)
                if match:
                    ips.append(match.group(1))

        # Unique IPs with count
        unique_ips = list(set(ips))
        return {
            "failed_logins_count": failed_count,
            "recent_failed_ips": unique_ips[:5]
        }
