from pathlib import Path
from migrator.utils import save_hosts_config, is_host_available, run_command
import subprocess
import os
import pwd
import grp
import paramiko


def create_nfs_localy(
    folder: str, client_ips: list[str], export_file: str = "/etc/exports"
):
    username = pwd.getpwuid(os.getuid()).pw_name
    primary_group = grp.getgrgid(os.getgid()).gr_name
    Path(folder).mkdir(parents=True, exist_ok=True)

    run_command(f"sudo chown -R {username}:{primary_group} {folder}")
    run_command(f"sudo chmod 755 {folder}")
    run_command("sudo chown -R 64055:109 {}".format(folder))

    for ip in client_ips:
        export_line = f"{folder} {ip}(rw,sync,no_subtree_check,no_root_squash)"

        with open(export_file, "r") as f:
            exports = f.read().splitlines()

        if export_line not in exports:
            run_command(f"echo '{export_line}' | sudo tee -a {export_file} > /dev/null")

    run_command("sudo exportfs -ra")
    save_hosts_config(client_ips=client_ips)


def create_nfs_remotely(
    host_ip: str, folder: str, client_ips: list[str], export_file: str = "/etc/exports"
):
    username = input("Enter SSH username: ").strip()

    print(f"Copying SSH key to {username}@{host_ip} ...")
    subprocess.run(
        f"ssh-copy-id -i ~/.ssh/id_rsa.pub {username}@{host_ip}", shell=True, check=True
    )

    with open("migrator/base_scripts/base_nfs_server_script.sh", "r") as f:
        script_content = f.read()

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    rsa_key = paramiko.RSAKey.from_private_key_file(str(Path.home() / ".ssh/id_rsa"))
    ssh_client.connect(hostname=host_ip, username=username, pkey=rsa_key)

    ssh_client.exec_command("mkdir -p /tmp/nfs_migrator")
    header = f"""#!/bin/bash
        CLIENT_IPS=({" ".join(f'"{ip}"' for ip in client_ips)})
        SHARED_DIR={folder}
        EXPORTS_FILE={export_file}

        """
    sftp = ssh_client.open_sftp()
    with sftp.file("/tmp/nfs_migrator/nfs_start.sh", "w") as remote_file:
        remote_file.write(header + script_content)
        remote_file.chmod(0o755)
    sftp.close()

    ssh_client.exec_command("sudo bash /tmp/nfs_migrator/nfs_start.sh")
    ssh_client.close()
    save_hosts_config(server_ip=host_ip, client_ips=client_ips)


def mount_nfs(host_ip: str, host_folder: str, local_folder: str):
    if not is_host_available(host_ip):
        raise RuntimeError(f"Host {host_ip} is not reachable")

    run_command("sudo apt install nfs-common")
    Path(local_folder).mkdir(parents=True, exist_ok=True)
    is_mounted = run_command(f"mountpoint -q {local_folder}", check=False)
    if is_mounted.returncode != 0:
        run_command(f"sudo mount -t nfs {host_ip}:{host_folder} {local_folder}")
    else:
        print(f"{local_folder} is already mounted")
    save_hosts_config(nfs_path=local_folder)


def unmount_nfs(local_folder: str):
    is_mounted = run_command(f"mountpoint -q {local_folder}", check=False)
    if is_mounted.returncode == 0:
        print(f"Unmounting {local_folder} ...")
        run_command(f"sudo umount -f -l {local_folder}")
        print(f"{local_folder} unmounted")
    else:
        print(f"{local_folder} is not mounted")
