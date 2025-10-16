# Deploy to Render - Complete Guide

This guide will help you deploy your Waste Detection App to Render.

## Project Structure
- **Backend**: Flask API (`/backend/`)
- **Frontend**: React app (`/frontend/`)
- **Database**: SQLite (included in backend)

## Prerequisites
1. A Render account (free tier available)
2. Your code pushed to GitHub
3. Optional: Gemini API key for AI features

## Deployment Steps

### Method 1: Using render.yaml (Recommended)
1. **Push your code to GitHub** (if not already done)
2. **Go to Render Dashboard** → New → Blueprint
3. **Connect your GitHub repository**
4. **Render will automatically detect the `render.yaml` file**
5. **Deploy!**

### Method 2: Manual Setup

#### Backend Service
1. **Go to Render Dashboard** → New → Web Service
2. **Connect your GitHub repository**
3. **Configure:**
   - **Name**: `waste-detection-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `cd backend && python app.py`
   - **Plan**: Free

#### Frontend Service
1. **Go to Render Dashboard** → New → Static Site
2. **Connect your GitHub repository**
3. **Configure:**
   - **Name**: `waste-detection-frontend`
   - **Build Command**: `cd frontend && npm ci && npm run build`
   - **Publish Directory**: `frontend/dist`
   - **Plan**: Free

## Environment Variables

Set these in your Render dashboard under "Environment":

### Required
- `FLASK_ENV=production`
- `FLASK_APP=app.py`
- `PORT=10000`

### Optional (for enhanced features)
- `GEMINI_API_KEY` - For AI-powered waste detection
- `GOOGLE_API_KEY` - Alternative AI API key
- `MAX_UPLOAD_MB=25` - Maximum file upload size
- `CORS_ORIGINS=*` - CORS configuration

### Email Features (Optional)
- `SMTP_HOST` - SMTP server
- `SMTP_PORT=587` - SMTP port
- `SMTP_USER` - Email username
- `SMTP_PASS` - Email password
- `SMTP_TLS=1` - Use TLS
- `MAIL_FROM` - From email address

## Post-Deployment

### 1. Update Frontend API URLs
After deployment, update your frontend to use the Render backend URL:

1. **Find your backend URL** (e.g., `https://waste-detection-backend.onrender.com`)
2. **Update API calls** in your frontend code to use this URL
3. **Redeploy the frontend**

### 2. Database Setup
- The SQLite database will be created automatically
- For production, consider upgrading to PostgreSQL (Render provides this)

### 3. File Storage
- Uploaded files are stored in the `/uploads` directory
- For production, consider using cloud storage (AWS S3, etc.)

## Troubleshooting

### Common Issues

1. **Build Failures**
   - Check that all dependencies are in `requirements.txt`
   - Ensure Python version compatibility

2. **CORS Errors**
   - Set `CORS_ORIGINS` to your frontend URL
   - Or use `*` for development (not recommended for production)

3. **File Upload Issues**
   - Check `MAX_UPLOAD_MB` setting
   - Ensure sufficient disk space

4. **Database Issues**
   - SQLite database is created automatically
   - Check file permissions

### Logs
- View logs in Render dashboard
- Backend logs show Flask application output
- Check for any error messages

## Scaling

### Free Tier Limitations
- **Sleep after 15 minutes** of inactivity
- **Limited CPU/RAM**
- **No persistent storage** (files may be lost)

### Upgrading
- **Starter Plan**: $7/month - No sleep, more resources
- **Standard Plan**: $25/month - Better performance
- **Pro Plan**: $85/month - High availability

## Security Considerations

1. **Environment Variables**: Never commit API keys to code
2. **CORS**: Restrict origins in production
3. **File Uploads**: Validate file types and sizes
4. **Database**: Consider upgrading to PostgreSQL for production

## Monitoring

- **Health Check**: `/health` endpoint available
- **Metrics**: Available in Render dashboard
- **Logs**: Real-time logs in dashboard

## Support

- **Render Documentation**: https://render.com/docs
- **Community**: https://community.render.com
- **Status Page**: https://status.render.com

---

## Quick Start Checklist

- [ ] Code pushed to GitHub
- [ ] Render account created
- [ ] Backend service deployed
- [ ] Frontend service deployed
- [ ] Environment variables set
- [ ] API URLs updated in frontend
- [ ] Test the application
- [ ] Set up monitoring

Your app should now be live on Render! 🚀