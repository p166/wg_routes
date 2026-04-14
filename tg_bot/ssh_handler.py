import paramiko
from typing import Tuple
from config import SSH_HOST, SSH_PORT, SSH_USER, SSH_KEY_PATH, S1_UPDATE_SCRIPT_PATH, S1_WG_DESTINATIONS_PATH, S1_WG_V6_ROUTES_PATH


class SSHHandler:
    def __init__(self):
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    def connect(self) -> bool:
        """Connect to S1 via SSH."""
        try:
            self.ssh_client.connect(
                hostname=SSH_HOST,
                port=SSH_PORT,
                username=SSH_USER,
                key_filename=SSH_KEY_PATH,
                timeout=10
            )
            return True
        except Exception as e:
            print(f"SSH connection error: {e}")
            return False
    
    def disconnect(self):
        """Close SSH connection."""
        self.ssh_client.close()
    
    def add_ips(self, ipv4_list: list, ipv6_list: list) -> Tuple[bool, str]:
        """Add IPs to wg_destinations.txt and wg_v6_routes.txt."""
        if not self.connect():
            return False, "❌ Ошибка подключения к S1"
        
        try:
            # Add IPv4
            if ipv4_list:
                for ip in ipv4_list:
                    cmd = f'echo "{ip}" >> {S1_WG_DESTINATIONS_PATH}'
                    stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
                    stdout.channel.recv_exit_status()
                    if stderr:
                        error = stderr.read().decode()
                        if error.strip():
                            return False, f"❌ Ошибка при добавлении IPv4: {error}"
            
            # Add IPv6
            if ipv6_list:
                for ip in ipv6_list:
                    cmd = f'echo "{ip}" >> {S1_WG_V6_ROUTES_PATH}'
                    stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
                    stdout.channel.recv_exit_status()
                    if stderr:
                        error = stderr.read().decode()
                        if error.strip():
                            return False, f"❌ Ошибка при добавлении IPv6: {error}"
            
            msg = f"✅ Добавлено:\n"
            if ipv4_list:
                msg += f"  • IPv4: {len(ipv4_list)} адресов\n"
            if ipv6_list:
                msg += f"  • IPv6: {len(ipv6_list)} адресов\n"
            msg += "\n⏳ Ожидайте команду /restart для применения"
            
            return True, msg
        
        except Exception as e:
            return False, f"❌ Ошибка SSH: {str(e)}"
        finally:
            self.disconnect()
    
    def restart_tunnel(self) -> Tuple[bool, str]:
        """Execute awg-quick down/up to restart tunnel."""
        if not self.connect():
            return False, "❌ Ошибка подключения к S1"
        
        try:
            # Method 1: Use update script if configured
            if S1_UPDATE_SCRIPT_PATH:
                cmd = f"sudo {S1_UPDATE_SCRIPT_PATH}"
            else:
                # Method 2: Direct awg-quick commands
                cmd = "sudo awg-quick down wg0 && sudo awg-quick up wg0"
            
            stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if exit_status != 0:
                error_msg = error if error else output
                return False, f"❌ Ошибка перезапуска: {error_msg}"
            
            return True, "✅ Туннель успешно перезапущен"
        
        except Exception as e:
            return False, f"❌ Ошибка SSH: {str(e)}"
        finally:
            self.disconnect()
    
    def get_destinations(self) -> Tuple[bool, str]:
        """Get current wg_destinations.txt from S1."""
        if not self.connect():
            return False, "❌ Ошибка подключения к S1"
        
        try:
            cmd = f"cat {S1_WG_DESTINATIONS_PATH}"
            stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                return False, "❌ Ошибка чтения файла"
            
            content = stdout.read().decode().strip()
            if not content:
                return True, "📄 Файл wg_destinations.txt пуст"
            
            lines = content.split('\n')
            lines = [l for l in lines if l.strip() and not l.startswith('#')]
            
            if not lines:
                return True, "📄 Файл wg_destinations.txt пуст (только комментарии)"
            
            msg = f"📄 <b>wg_destinations.txt</b> ({len(lines)} строк):\n\n"
            msg += "<code>" + "\n".join(lines[:50]) + "</code>"  # Show first 50 lines
            
            if len(lines) > 50:
                msg += f"\n\n... и еще {len(lines) - 50} строк"
            
            return True, msg
        
        except Exception as e:
            return False, f"❌ Ошибка SSH: {str(e)}"
        finally:
            self.disconnect()
