from migrator.utils import run_command, read_hosts_config, save_hosts_config
import os
import typer
from pathlib import Path
import json
from urllib.parse import urlparse


def delete_nfs_vm(vm_name: str):
    config = read_hosts_config()
    if not config or "nfs_path" not in config or config["nfs_path"] == "":
        print("No NFS configuration found. Please run the setup command first.")
        raise typer.BadParameter()
    nfs_path = Path(config["nfs_path"])
    vm_image = nfs_path / f"{vm_name}.img"
    if vm_image.exists():
        run_command(f"sudo virsh destroy {vm_name}")
        run_command(f"sudo virsh undefine {vm_name} --remove-all-storage")
        print(f"Deleted VM image: {vm_image}")
    else:
        print(f"VM {vm_image} does not seem exist. Nothing to delete.")
    available_vms = config["vm_names"]
    available_vms.remove(vm_name)
    save_hosts_config(vm_names=available_vms)


def create_vm_on_nfs(
    vm_name: str, image_path: str, image_name: str, disk_size: int, ram_size: int
):
    config = read_hosts_config()
    if not config or "nfs_path" not in config or config["nfs_path"] == "":
        print("No NFS configuration found. Please run the setup command first.")
        raise typer.BadParameter()
    nfs_path = Path(config["nfs_path"])
    image_path = get_path_to_image(image_path, image_name, nfs_path)
    run_command(f"qemu-img create -f raw {nfs_path/vm_name}.img {disk_size}G")

    _create_vm(
        vm_name,
        image_name,
        nfs_path / image_path,
        disk_size,
        ram_size,
        nfs_path / f"{vm_name}.img",
    )
    save_hosts_config(vm_names=config["vm_names"] + [vm_name])


def _create_vm(
    vm_name: str,
    image_name: str,
    image_path: str,
    disk_size: int,
    ram_size: int,
    disk_path: str,
):
    virt_command = f"sudo virt-install --name {vm_name} --os-type linux --os-variant {image_name} --ram {ram_size} --disk {disk_path},device=disk,bus=virtio,size={disk_size},format=qcow2 --graphics vnc,listen=0.0.0.0 --noautoconsole --hvm --cdrom {image_path} --boot cdrom,hd"
    run_command(virt_command, check=True)


def run_wget(url: str, dest_dir: str):
    filename = os.path.basename(urlparse(url).path)
    run_command(f"wget {url} -O {Path(dest_dir)/filename}", check=True)
    return filename


def get_path_to_image(image_path, image_name, nfs_path):
    if not os.path.isfile(image_path):
        if not os.path.isfile(f"{nfs_path}/images/config.json"):
            Path(f"{nfs_path}/images").mkdir(parents=True, exist_ok=True)
            images_config = {}
        else:
            with open(f"{nfs_path}/images/config.json", "r") as f:
                images_config = json.load(f)
        if image_name in images_config:
            image_path = images_config[image_name]["image_path"]
        else:
            image_url = image_path
            image_path = (
                f"{nfs_path}/images/{run_wget(image_url, f'{nfs_path}/images/')}"
            )
            images_config[image_name] = {
                "image_path": image_path.removeprefix(str(nfs_path)),
                "image_url": image_url,
            }
            with open(f"{nfs_path}/images/config.json", "w") as f:
                json.dump(images_config, f, indent=4)
    return image_path
