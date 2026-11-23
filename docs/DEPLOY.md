# Deployment Guide

This guide covers deploying the video editing engine to a public URL for the live demo requirement.

---

## Option A: VPS with Docker (Recommended)

### Prerequisites
- A VPS (DigitalOcean Droplet, Linode, AWS EC2, Hetzner, etc.) — $5–10/month
- Ubuntu 22.04 LTS
- A domain name or static IP

### Steps

```bash
# 1. SSH into your VPS
ssh root@YOUR_VPS_IP

# 2. Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker

# 3. Clone your repo
git clone https://github.com/YOUR_USERNAME/prompt-video-editor.git
cd prompt-video-editor

# 4. Configure environment
cp .env.example .env
# Edit .env:
#   API_TOKEN=<a long random secret — keep this>
#   BASE_URL=https://your-domain.com

# 5. Start the stack
docker compose up -d --build

# 6. Verify
curl http://localhost:8000/health

# 7. Set up HTTPS with Caddy (reverse proxy)
apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy

# /etc/caddy/Caddyfile:
cat > /etc/caddy/Caddyfile << 'EOF'
your-domain.com {
    reverse_proxy localhost:8000
}
EOF

systemctl reload caddy
```

### Verify from another network

```bash
curl https://your-domain.com/health
# Should return: {"status": "ok", "version": "1.0.0"}
```

---

## Option B: Railway / Render.com (PaaS — no VPS needed)

### Railway

1. Sign up at [railway.app](https://railway.app)
2. New Project → Deploy from GitHub → select your repo
3. Set environment variables: `API_TOKEN`, `BASE_URL`
4. Railway auto-detects the `Dockerfile` — click Deploy
5. Add a custom domain or use the generated `.railway.app` URL

**Note**: Railway's free tier has an ephemeral filesystem — uploaded videos will not persist across deploys. For the demo, upload the video fresh each time, or use Railway's persistent volume add-on.

### Render.com

1. Sign up at [render.com](https://render.com)
2. New → Web Service → Connect GitHub
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:get_app --factory --host 0.0.0.0 --port $PORT`
5. Set environment variables in the Render dashboard

---

## Option C: Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# In your project directory:
fly launch        # follow prompts; Dockerfile is auto-detected
fly secrets set API_TOKEN=your-long-secret
fly deploy
```

---

## Keeping the Demo Alive

- Do not stop or redeploy between submission and results announcement
- Note any cold-start delay (some PaaS services sleep after inactivity)
- Keep the `API_TOKEN` unchanged — paste it in the submission form

---

## Security Notes

- Never commit `.env` to the repository (it is in `.gitignore`)
- The `API_TOKEN` is currently optional in this implementation; add middleware to enforce it in production
- If using a public URL, consider rate limiting (`slowapi` or nginx limit_req)
