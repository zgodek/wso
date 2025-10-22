from pathlib import Path
from migrator.utils import (
    save_hosts_config,
    read_hosts_config,
    get_local_ip,
    is_host_available,
)
from enum import Enum
import subprocess
import time
import getpass
import logging
import tempfile
import filecmp
import os


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


class VMStatus(Enum):
    SUCCESS = 0
    STILL_RUNNING = 1
    ERROR_RETRY = 2 


#TODO remove ssh login use ssh keys


def log_info_before(vm_name: str, host_ip=None):
    if host_ip is not None:
        logging.info(
            f"Before attempting to migrate {vm_name} from {host_ip} please make sure ssh connection is enabled on this machine and firewall is properly configured."
        )
        logging.info(
            f"Please make sure that remote ssh key from {host_ip} is added to your local machine."
        )
    else:
        logging.info(
            f"Before attempting to migrate {vm_name} please make sure ssh connection is enabled on every VM host in local network and firewall is properly configured."
        )


def get_field_from_config(field_name: str):
    config = read_hosts_config()
    if field_name not in config:
        field_input = input(f"Enter value for {field_name}: ").strip()
        save_hosts_config(**{field_name: field_input})
        return field_input
    else:
        return config[field_name]


def look_for_vm_image(host_ip: str, img_name: str, ssh_user: str, password: str):
    logging.info(f"Searching for {img_name} on remote host {host_ip}...")
    find_command = [
        "sshpass", "-p", password, "ssh", f"{ssh_user}@{host_ip}",
        f"sudo -S find / -type f -name {img_name} 2>/dev/null"
    ]
    find_result = subprocess.run(find_command, input=password + "\n", capture_output=True, text=True)
    if find_result.returncode != 0 and ("permission denied" in find_result.stderr.lower() or "authentication failed" in find_result.stderr.lower()):
        raise RuntimeError(f"SSH authentication failed: {find_result.stderr.strip()}")
    if not find_result.stdout.strip():
        raise FileNotFoundError(f"Could not find VM image named '{img_name}' on {host_ip}.")

    return find_result.stdout.strip().splitlines()[0]


def copy_vm_xml_config(host_ip: str, vm_name: str, ssh_user: str, password: str):
    logging.info(f"Fetching VM xml config from {host_ip}...")                 

    xml_path = f"{get_field_from_config('xml_folder')}/{vm_name}.xml"

    virsh_dump_remote_cmd = f'sshpass -p {password} ssh {ssh_user}@{host_ip} "virsh -c qemu:///system dumpxml {vm_name} > {xml_path}"'
    virsh_dump_remote_result = subprocess.run(virsh_dump_remote_cmd, shell=True, capture_output=True, text=True)

    xml_scp_command = [
        "sshpass", "-p", password,
        "scp", f"{ssh_user}@{host_ip}:{xml_path}", xml_path
    ]
    xml_scp_result = subprocess.run(xml_scp_command, input=password + "\n", capture_output=True, text=True)

    if virsh_dump_remote_result.returncode == 0 and xml_scp_result.returncode == 0:
        logging.info(f"VM config created and copied to {xml_path}")
    elif xml_scp_result.returncode != 0:
        raise RuntimeError(f"Failed to copy xml config:\n{xml_scp_result.stderr}")
    elif virsh_dump_remote_result.returncode != 0:
        raise RuntimeError(f"Failed to export VM xml config:\n{virsh_dump_remote_result.stderr}")
    
    return xml_path


def start_vm(vm_name: str):
    logging.info("Starting VM locally...")
    start_cmd = ["virsh", "start", vm_name]
    start_result = subprocess.run(start_cmd, capture_output=True, text=True)
    if start_result.returncode != 0:
        raise RuntimeError(f"Failed to start VM:\n{start_result.stderr}")
    else:
        logging.info(f"VM '{vm_name}' started successfully.")


def is_vm_defined(vm_name: str) -> bool:
    try:
        result = subprocess.run(
            ["virsh", "dominfo", vm_name],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        raise RuntimeError(f"Failed to check VM definition: {e}")


def define_vm(vm_name: str, xml_path: str):
    needs_defining = True

    if is_vm_defined(vm_name=vm_name):
        with tempfile.NamedTemporaryFile(delete=False) as tmp_current:
            tmp_current_path = tmp_current.name
            virsh_dump_local_cmd = f"virsh dumpxml {vm_name}"
            virsh_dump_local_result = subprocess.run(virsh_dump_local_cmd, shell=True, stdout=tmp_current, stderr=subprocess.PIPE, text=True)
            if virsh_dump_local_result.returncode != 0:
                logging.warning(f"Failed to dump current local VM definition: {virsh_dump_local_result.stderr.strip()}")
                tmp_current_path = None

        if tmp_current_path and os.path.exists(xml_path):
            if filecmp.cmp(tmp_current_path, xml_path, shallow=False):
                logging.info(f"No changes detected in VM xml for {vm_name}, skipping redefine.")
                needs_defining = False
            else:
                logging.info(f"Changes detected in VM xml for {vm_name}, proceeding with redefine.")
                virsh_undefine_cmd = f"virsh undefine {vm_name}"
                virsh_undefine_result = subprocess.run(virsh_undefine_cmd, shell=True, capture_output=True, text=True)
                if virsh_undefine_result.returncode != 0:
                    raise RuntimeError(f"Failed to undefine VM locally: {virsh_undefine_result.stderr}")            

    if needs_defining:
        virsh_define_cmd = f"virsh define {xml_path}"
        virsh_define_result = subprocess.run(virsh_define_cmd, shell=True, capture_output=True, text=True)
        if virsh_define_result.returncode != 0:
            raise RuntimeError(f"Failed to define VM locally: {virsh_define_result.stderr}")

        logging.info(f"Successfully defined {vm_name} locally.")


def remote_image_in_use(host_ip: str, user: str, image_path: str, password: str) -> VMStatus:
    logging.info(f"Checking if image: {image_path} is in use on host: {host_ip}...")
    try:
        fuser_command = ["sshpass", "-p", password, "ssh", f"{user}@{host_ip}", f"sudo -S fuser {image_path}"]
        fuser_result = subprocess.run(
            fuser_command,
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if fuser_result.returncode == 0:
            return VMStatus.STILL_RUNNING
        elif fuser_result.returncode != 0:
            if "permission denied" in fuser_result.stderr.lower() or "authentication failed" in fuser_result.stderr.lower():
                raise RuntimeError("SSH authentication failed")
            return VMStatus.SUCCESS
    except Exception as e:
        logging.error(f"Error connecting to {host_ip}: {e}")
        return VMStatus.ERROR_RETRY


def shutdown_remote_vm(host_ip: str, user: str, image_path: str, password: str) -> VMStatus:
    vm_name = Path(image_path).stem
    logging.info(f"Attempting to shut down VM '{vm_name}' on host {host_ip} via SSH...")
    try:
        virsh_shutdown_command = ["sshpass", "-p", password, "ssh", f"{user}@{host_ip}", f"sudo -S virsh shutdown {vm_name}"]
        virsh_shutdown_result = subprocess.run(
            virsh_shutdown_command,
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if virsh_shutdown_result.returncode == 1:
            if "permission denied" in virsh_shutdown_result.stderr.lower() or "authentication failed" in virsh_shutdown_result.stderr.lower():
                raise RuntimeError("SSH authentication failed")
            return VMStatus.ERROR_RETRY

        logging.info("Waiting for VM to shut down...")
        for _ in range(12):
            time.sleep(5)
            if remote_image_in_use(host_ip, user, image_path, password) == VMStatus.SUCCESS:
                logging.info("Image is not in use on any remote hosts.")
                return VMStatus.SUCCESS
            logging.info("Still in use... waiting")
        raise RuntimeError("Image still in use after shutdown attempt.")
    except Exception as e:
        logging.error(f"Unexpected error occurred: {e}")
        return VMStatus.ERROR_RETRY



def run_vm_nfs(img_name: str):
    log_info_before(vm_name=vm_name)
    mount_path = get_field_from_config("nfs_path")
    full_image_path = Path(mount_path) / img_name

    if not full_image_path.exists():
        raise FileNotFoundError(f"Image not found: {full_image_path}")

    vm_name = full_image_path.stem
    full_image_path = str(full_image_path)
    local_ip = get_local_ip()

    host_ips = get_field_from_config("client_ips")
    for host_ip in host_ips:
        if host_ip == local_ip:
            logging.info(f"Skipping local host: {host_ip}")
            continue
        logging.info(f"Checking if {img_name} is in use on {host_ip}...")
        image_in_use_result = VMStatus.ERROR_RETRY
        while image_in_use_result == VMStatus.ERROR_RETRY:
            ssh_user = input(f"Enter SSH username for {host_ip}: ").strip()
            password = getpass.getpass(f"Sudo password for {ssh_user}@{host_ip}: ")
            image_in_use_result = remote_image_in_use(host_ip, ssh_user, full_image_path, password)
            if image_in_use_result == VMStatus.STILL_RUNNING:
                logging.info(f"Image {img_name} is in use on {host_ip}")
                if shutdown_remote_vm(host_ip, ssh_user, full_image_path, password) == VMStatus.ERROR_RETRY:
                    raise RuntimeError("Couldn't shut down remote VM.")

                xml_path = copy_vm_xml_config(host_ip=host_ip, vm_name=vm_name, ssh_user=ssh_user, password=password)
                define_vm(vm_name=vm_name, xml_path=xml_path)
                break

    start_vm(vm_name=vm_name)


def run_vm_scp(host_ip: str, img_name: str):
    vm_name = img_name.rsplit(".", 1)[0]
    log_info_before(vm_name=vm_name, host_ip=host_ip)
    local_dest_dir = Path(get_field_from_config("local_vm_path"))

    local_dest_dir.mkdir(parents=True, exist_ok=True)
    local_dest = local_dest_dir / img_name

    ssh_user = input(f"Enter SSH username for {host_ip}: ").strip()
    password = getpass.getpass(f"Sudo password for {ssh_user}@{host_ip}: ")

    remote_path = look_for_vm_image(host_ip=host_ip, img_name=img_name, ssh_user=ssh_user, password=password)

    image_in_use_result = remote_image_in_use(host_ip, ssh_user, remote_path, password)
    if image_in_use_result == VMStatus.STILL_RUNNING:
        logging.info(f"Image {img_name} is in use on {host_ip}")
        if shutdown_remote_vm(host_ip, ssh_user, remote_path, password) == VMStatus.ERROR_RETRY:
            raise RuntimeError("Couldn't shut down remote VM.")
    logging.info(f"Starting SCP of image {remote_path}...")

    vm_scp_command = [
        "sshpass", "-p", password,
        "scp",
        f"{ssh_user}@{host_ip}:{remote_path}",
        str(local_dest)
    ]
    vm_scp_result = subprocess.run(vm_scp_command, input=password + "\n", capture_output=True, text=True)

    if vm_scp_result.returncode == 0:
        logging.info(f"VM image copied to {local_dest}")
    else:
        raise RuntimeError(f"Failed to copy VM image:\n{vm_scp_result.stderr}")


    xml_path = copy_vm_xml_config(host_ip=host_ip, vm_name=vm_name, ssh_user=ssh_user, password=password)

    define_vm(vm_name=vm_name, xml_path=xml_path)

    start_vm(vm_name=vm_name)


def migrate_live_local(vm_name: str, host_ip: str):
    log_info_before(vm_name=vm_name, host_ip=host_ip)
    if not is_host_available(host_ip):
        raise RuntimeError(f"Host {host_ip} is not reachable")

    ssh_user = input(f"Enter SSH username for {host_ip}: ").strip()
    password = getpass.getpass(f"Sudo password for {ssh_user}@{host_ip}: ")
    current_ip = get_local_ip()

    virsh_command = [
        "ssh",
        f"{ssh_user}@{host_ip}",
        "sudo",
        "-S",
        "virsh", "migrate",
        "--live", "--persistent", "--unsafe", "--verbose",
        "--copy-storage-all",
        f"{vm_name}",
        f"qemu+ssh://{ssh_user}@{current_ip}/system",
        "--migrateuri", f"tcp://{ssh_user}@{current_ip}:49153"
    ]

    virsh_result = subprocess.run(
        virsh_command,
        input=password + "\n",
        capture_output=True,
        text=True,
    )

    if virsh_result.returncode == 0:
        logging.info(f"Machine migrated successfully.\n{virsh_result}")
    else:
        raise RuntimeError(f"Failed to copy VM image:\n{virsh_result.stderr}")


def migrate_live_nfs(vm_name: str, host_ip: str):
    log_info_before(vm_name=vm_name, host_ip=host_ip)
    if not is_host_available(host_ip):
        raise RuntimeError(f"Host {host_ip} is not reachable")
    config = read_hosts_config()
    if not os.path.exists(Path(config["nfs_path"]) / f"{vm_name}.img"):
        raise RuntimeError(f"Remote NFS path {config['nfs_path']}/{f'{vm_name}.img'} does not exist")

    ssh_user = input(f"Enter SSH username for {host_ip}: ").strip()
    password = getpass.getpass(f"Sudo password for {ssh_user}@{host_ip}: ")
    current_ip = get_local_ip()

    virsh_command = [
        "ssh",
        f"{ssh_user}@{host_ip}",
        "sudo",
        "-S",
        "virsh", "migrate",
        "--live", "--persistent", "--unsafe", "--verbose",
        f"{vm_name}",
        f"qemu+ssh://{ssh_user}@{current_ip}/system",
        "--migrateuri", f"tcp://{ssh_user}@{current_ip}:49152"
    ]

    virsh_result = subprocess.run(
        virsh_command,
        input=password + "\n",
        capture_output=True,
        text=True,
    )

    if virsh_result.returncode == 0:
        logging.info(f"Machine migrated successfully.\n{virsh_result}")
    else:
        raise RuntimeError(f"Failed to copy VM image:\n{virsh_result.stderr}")
