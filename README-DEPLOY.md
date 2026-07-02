# By the fruit Deployment Guide

**Host Nginx + Docker Frontend + Docker Backend**

This document describes how to deploy the By the fruit application on a server that already hosts other websites using **host-level Nginx**, while keeping the backend fully containerized.

> **Key rule:**  
> Only the **host Nginx** listens on ports **80 and 443**.  
> Docker containers run behind it on internal ports and networks.

---

## Architecture Overview

```
Internet
   |
   v
Host Nginx (80 / 443, SSL termination)
   |
   v
Backend Container (Django/API :8000, internal only)
```

---

## Prerequisites

- Linux server with Nginx, Docker, Certbot
- DNS records:
  - api-bythefruit.oddshoesdev.xyz

## 1. Install Docker and Create Docker Network

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

docker network create app-network

sudo usermod -aG docker $USER

echo "YOUR_ACCESS_TOKEN" | docker login -u YOUR_USERNAME --password-stdin

```

---
## 2. Create and run redis container

```bash
docker run -d --name redis --network app-network -p 6379:6379 --restart unless-stopped redis:alpine
```

### 3. Create migration folders on the root server

```bash
cd /home/main
sudo mkdir -p migrations/accounts migrations/profiles migrations/api 
sudo touch migrations/__init__.py
sudo touch migrations/api/__init__.py
sudo touch migrations/accounts/__init__.py
sudo touch migrations/profiles/__init__.py
```

---
## 3. Host Nginx Config – API

Create `/etc/nginx/sites-available/api-bythefruit.oddshoesdev.xyz`

```nginx
server {
    listen 80;
    server_name api-bythefruit.oddshoesdev.xyz;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name api-bythefruit.oddshoesdev.xyz;

    ssl_certificate etc/letsencrypt/live/api-bythefruit.oddshoesdev.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api-bythefruit.oddshoesdev.xyz/privkey.pem;

    location /static/ {
        alias /home/main/static/;
    }

    location /media/ {
        alias /home/main/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:7080;
    }
}
```

---

## 7. SSL Certificates

```bash
sudo certbot --nginx -d api-bythefruit.oddshoesdev.xyz
```

---

## 8. Reload Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## Summary

- Host Nginx owns ports 80/443
- Frontend container serves UI and proxies API
- Backend container is internal only
- Other host sites remain unaffected
