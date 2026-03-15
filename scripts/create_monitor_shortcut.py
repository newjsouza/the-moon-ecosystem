import os
import subprocess

def create_desktop_shortcut():
    desktop_path = os.path.expanduser("~/Área de trabalho")
    shortcut_path = os.path.join(desktop_path, "MoonMonitor.desktop")
    
    # Ensure the directory exists (handling different locales)
    if not os.path.exists(desktop_path):
        desktop_path = os.path.expanduser("~/Desktop")
        shortcut_path = os.path.join(desktop_path, "MoonMonitor.desktop")

    content = f"""[Desktop Entry]
Name=The Moon Monitor
Comment=Visual Monitor for Agent Workspace
Exec=xdg-open http://localhost:3000
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=Development;
"""
    
    try:
        with open(shortcut_path, "w") as f:
            f.write(content)
        os.chmod(shortcut_path, 0o755)
        
        # Mark as trusted using gio (metadata::trusted true)
        try:
            # Try both 'true' and 'yes' just in case, but 'true' is preferred in newer GNOME
            subprocess.run(["gio", "set", "-t", "string", shortcut_path, "metadata::trusted", "true"], check=True)
            print(f"Atalho marcado como confiável via GIO (true).")
        except Exception as gio_err:
            print(f"Aviso: Falha ao usar GIO: {gio_err}")

        # Mark as trusted using DBus (Specific for Zorin/DING extension)
        try:
            dbus_cmd = [
                "dbus-send", "--session", "--dest=org.gnome.Shell", 
                "--type=method_call", "/org/gnome/Shell/Extensions/DING", 
                "org.gnome.Shell.Extensions.DING.MarkTrusted", 
                f"string:file://{shortcut_path}"
            ]
            subprocess.run(dbus_cmd, check=True)
            print(f"Notificação DBus enviada para a extensão DING.")
        except Exception as dbus_err:
            print(f"Aviso: Falha na chamada DBus (pode não ser necessário se o GIO funcionou): {dbus_err}")

        # Also register in applications menu
        apps_path = os.path.expanduser("~/.local/share/applications")
        os.makedirs(apps_path, exist_ok=True)
        app_shortcut = os.path.join(apps_path, "MoonMonitor.desktop")
        
        try:
            with open(app_shortcut, "w") as f:
                f.write(content)
            os.chmod(app_shortcut, 0o755)
            # Registering metadata for menu shortcut too
            subprocess.run(["gio", "set", "-t", "string", app_shortcut, "metadata::trusted", "true"], check=False)
            print(f"Atalho adicionado ao menu de aplicativos: {app_shortcut}")
        except Exception as e:
            print(f"Aviso: Não foi possível adicionar ao menu: {e}")
            
        print(f"Atalho criado em: {shortcut_path}")
    except Exception as e:
        print(f"Erro ao criar atalho: {e}")

if __name__ == "__main__":
    create_desktop_shortcut()
