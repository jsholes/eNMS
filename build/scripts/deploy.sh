#!/bin/bash

function install() {
  if [ "$install" = "vault" ]; then
    sudo apt-get install -y unzip
    find . -iname "*zip" -exec unzip {} \;
    sudo ln -s ${path:-$PWD}/vault /usr/bin/vault
    sudo ln -s ${path:-$PWD}/consul /usr/bin/consul
    nohup consul agent -dev &
    config='
      disable_mlock = true

      storage "consul" {
        address = "127.0.0.1:8500"
        path    = "vault/"
      }

      listener "tcp" {
        address     = "0.0.0.0:8200"
        tls_disable = 1
      }
    '
    nohup vault server -config=<(echo "$config") &
    export VAULT_ADDR=http://127.0.0.1:8200 && sleep 10
    echo $(vault operator init | head -n7)
  elif [ "$install" = "mysql" ]; then
    sudo apt install -y mysql-server python3-mysqldb
    sudo pip3 install mysqlclient
    sudo mysql -u root --password=password -e 'CREATE DATABASE enms;'
    sudo mysql -u root --password=password -e 'set global max_connections = 2000;'
  elif [ "$install" = "postgresql" ]; then
    sudo apt-get install -y postgresql libpq-dev postgresql-client
    sudo pip3 install psycopg2
    sudo -u postgres psql -c "CREATE DATABASE enms;"
    sudo -u postgres psql -c "CREATE USER root WITH PASSWORD 'password';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE enms TO root;"
  elif [ "$install" = "enms" ]; then
    sudo apt-get install -y python3-pip sshpass npm
    for file in build/requirements/*; do pip3 install -r $file; done
    sudo npm install -g prettier eslint eslint-config-google
  elif [ "$install" = "nginx" ]; then
    sudo apt-get install -y nginx
    sudo cp ${path:-$PWD}/build/nginx/enms.conf /etc/nginx/sites-enabled
    sudo systemctl restart nginx
  fi
}

function uninstall() {
  if [ "$uninstall" = "vault" ]; then
    consul leave
    kill $(ps aux | awk '/vault server/ {print $2}' | head -1)
    sudo rm /usr/bin/{vault,consul}
    rm ${path:-$PWD}/{vault,consul} nohup.out
  elif [ "$uninstall" = "mysql" ]; then
    sudo apt-get -y remove --purge "mysql*"
  elif [ "$uninstall" = "postgresql" ]; then
    sudo apt-get -y --purge remove postgresql\* libpq-dev
  elif [ "$uninstall" = "nginx" ]; then
    sudo nginx -s stop
    sudo apt-get -y remove --purge nginx
    sudo rm /etc/nginx/sites-enabled/enms.conf
  fi
  sudo apt-get -y autoremove
  sudo apt-get -y autoclean
}


function deploy() {
  cd ${path:-$PWD}
  if [[ -n "$install" ]]; then
    install
  elif [[ -n "$uninstall" ]]; then
    uninstall
  fi
}

function help() {
  echo "
    Usage: $(basename $0) [OPTIONS]

    Options:
      -h                           Help
      -i <program>                 Install
      -p <path>                    Path to folder (default: current folder \$PWD)
      -u <program>                 Uninstall

    Programs:
      MySQL / PostgreSQL
      Vault
      eNMS (git, pip, requirements)
      Nginx
  "
  exit 0
}

while getopts h?p:i:u: opt; do
    case "$opt" in
      i) install=${OPTARG,,};;
      p) path=$OPTARG;;
      u) uninstall=${OPTARG,,};;
      h|\?) help;;
    esac
done

deploy
