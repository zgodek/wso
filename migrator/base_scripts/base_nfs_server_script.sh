USERNAME=$(whoami)
PRIMARY_GROUP=$(id -gn)

sudo mkdir -p $SHARED_DIR

sudo chown -R $USERNAME:$PRIMARY_GROUP $SHARED_DIR
sudo chmod 755 $SHARED_DIR
sudo chown -R 64055:109 $SHARED_DIR

for IP in "${CLIENT_IPS[@]}"; do
    EXPORT_LINE="$SHARED_DIR $IP(rw,sync,no_subtree_check,no_root_squash)"

    if ! grep -Fxq "$EXPORT_LINE" "$EXPORTS_FILE"; then
        echo "$EXPORT_LINE" | sudo tee -a "$EXPORTS_FILE" > /dev/null
    else
        echo "Export for $IP already exists"
    fi
done

sudo exportfs -ra

