#! /bin/bash

AMN_PATH=/etc/amnezia/amneziawg/

sudo mkdir -p $AMN_PATH
sudo cp ./amnezia_for_awg.conf $AMN_PATH/wg0.conf
sudo add-apt-repository ppa:amnezia/ppa
sudo apt install -y dig software-properties-common python3-launchpadlib gnupg2 linux-headers-$(uname -r)
sudo apt install -y amneziawg
sudo cp ./wg_destinations.txt $AMN_PATH/
sudo cp ./wg_destinations_16.txt $AMN_PATH/
sudo cp ./wg_destinations_24.txt $AMN_PATH/
sudo awg setconf wg0 $AMN_PATH/wg0.conf
sudo systemctl enable --now awg-quick@wg0
