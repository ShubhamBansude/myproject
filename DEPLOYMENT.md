# 🚀 Waste Rewards App - Mobile Deployment Guide

This guide will help you deploy your Waste Rewards app so that mobile users can access it via a sharable link.

## 📱 Mobile Features

Your app is already optimized for mobile with:
- ✅ **Progressive Web App (PWA)** - Installable on mobile devices
- ✅ **Mobile Camera Support** - Direct camera access for waste detection
- ✅ **Touch-Friendly UI** - Responsive design for all screen sizes
- ✅ **Offline Support** - Works even with poor connectivity
- ✅ **Video Recording** - Mobile video capture for waste disposal verification

## 🛠️ Quick Deployment

### Prerequisites

1. **Docker** - [Install Docker](https://docs.docker.com/get-docker/)
2. **Docker Compose** - Usually included with Docker Desktop

### One-Command Deployment

```bash
# Make the script executable and run it
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Check for Docker installation
2. Create environment configuration
3. Build and start all services
4. Provide you with sharable links

### Manual Deployment

If you prefer manual control:

```bash
# 1. Create environment file
cp .env.example .env
# Edit .env with your settings

# 2. Build and start services
docker-compose up -d

# 3. Check status
docker-compose ps
```

## 🌐 Access Your App

After deployment, your app will be available at:

- **Local Access**: `http://localhost:8080`
- **Public Access**: `http://YOUR_SERVER_IP:8080`
- **Mobile Access**: Same as public access - works on all devices!

## 📱 Mobile User Experience

### For Your Friends (Mobile Users):

1. **Open the link** on their mobile device
2. **Install the app** - They'll see an "Add to Home Screen" prompt
3. **Create account** - Simple signup process
4. **Start earning points** by:
   - Taking photos of waste
   - Recording videos of waste disposal
   - Scanning items for recycling

### Mobile-Specific Features:

- **Camera Integration**: Direct access to phone camera
- **Video Recording**: Record waste disposal process
- **Touch Gestures**: Swipe, tap, pinch-to-zoom
- **Offline Mode**: Works without internet connection
- **Push Notifications**: Get notified about rewards and missions

## 🔧 Configuration

### Environment Variables (.env file):

```bash
# Required
FLASK_ENV=production
PORT=5000

# Optional but recommended
GEMINI_API_KEY=your_api_key_here  # For AI features
CORS_ORIGINS=*                    # Allow all origins
MAX_UPLOAD_MB=25                  # File upload limit
```

### Getting a Gemini API Key (Optional):

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Add it to your `.env` file

## 🚀 Production Deployment

### For Cloud Deployment:

#### Option 1: VPS/Cloud Server
```bash
# On your server
git clone <your-repo>
cd <your-repo>
./deploy.sh
```

#### Option 2: Docker Hosting Services
- **Railway**: Connect GitHub repo, auto-deploy
- **Render**: Connect repo, set build command to `docker-compose up`
- **DigitalOcean App Platform**: Connect repo, auto-detect Docker

#### Option 3: Traditional VPS
```bash
# Install Docker on Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Deploy your app
./deploy.sh
```

## 📊 Monitoring & Management

### View Logs:
```bash
docker-compose logs -f
```

### Restart Services:
```bash
docker-compose restart
```

### Update App:
```bash
git pull
docker-compose build
docker-compose up -d
```

### Stop App:
```bash
docker-compose down
```

## 🔒 Security Considerations

1. **Change default passwords** in production
2. **Use HTTPS** in production (consider Cloudflare or Let's Encrypt)
3. **Limit file uploads** (already configured)
4. **Regular updates** of dependencies

## 📱 PWA Installation

Your app is a Progressive Web App, which means:

- **Installable**: Users can install it like a native app
- **Offline**: Works without internet connection
- **Push Notifications**: Can send notifications
- **App-like Experience**: Full-screen, no browser UI

### How Users Install:

1. Open the app in mobile browser
2. Look for "Add to Home Screen" prompt
3. Tap "Add" to install
4. App appears on home screen like a native app

## 🎯 Sharing Your App

### Share the Link:
```
http://YOUR_SERVER_IP:8080
```

### QR Code (Optional):
Generate a QR code for the link to make sharing easier.

### Social Media:
- Share screenshots of the app
- Post the link with description
- Encourage friends to try it

## 🆘 Troubleshooting

### Common Issues:

1. **Port already in use**:
   ```bash
   # Change port in docker-compose.yml
   ports:
     - "8081:80"  # Use different port
   ```

2. **Permission denied**:
   ```bash
   sudo chmod +x deploy.sh
   ```

3. **Docker not found**:
   - Install Docker Desktop
   - Restart terminal/computer

4. **App not loading**:
   ```bash
   docker-compose logs frontend
   docker-compose logs backend
   ```

### Getting Help:

1. Check logs: `docker-compose logs`
2. Verify services: `docker-compose ps`
3. Test endpoints: `curl http://localhost:8080/api/stats`

## 🎉 Success!

Once deployed, your friends can:
- ✅ Access the app on any device
- ✅ Create accounts and start earning points
- ✅ Use all features including camera and video
- ✅ Install it as a mobile app
- ✅ Work offline

**Your sharable link**: `http://YOUR_SERVER_IP:8080`

Happy sharing! 🌍♻️
