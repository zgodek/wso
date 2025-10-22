#!/bin/bash

CLIENT_IPS=("192.168.100.31" "192.168.100.82")
SHARED_DIR=/mnt/nfsshare
USERNAME=$(whoami)
PRIMARY_GROUP=$(id -gn)
EXPORTS_FILE=/etc/exports

sudo mkdir -p $SHARED_DIR

#sudo groupadd -g 109 kvm
#sudo useradd -u 64055 -g 109 libvirt-qemu

sudo chown -R $USERNAME:$PRIMARY_GROUP $SHARED_DIR
sudo chmod 755 $SHARED_DIR
sudo chown -R 64055:109 $SHARED_DIR #i got this by running id libvirt-qemu in vm host machine

for IP in "${CLIENT_IPS[@]}"; do
    EXPORT_LINE="$SHARED_DIR $IP(rw,sync,no_subtree_check,no_root_squash)"
    
    if ! grep -Fxq "$EXPORT_LINE" "$EXPORTS_FILE"; then
        echo "$EXPORT_LINE" | sudo tee -a "$EXPORTS_FILE" > /dev/null
    else
        echo "Export for $IP already exists"
    fi
done

sudo exportfs -ra

