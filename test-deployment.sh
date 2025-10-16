#!/bin/bash

# Test script to verify deployment is working

echo "🧪 Testing Waste Rewards App Deployment..."

# Test if services are running
echo "📊 Checking service status..."
docker-compose ps

# Test backend health
echo "🔍 Testing backend health..."
if curl -s http://localhost:8080/api/stats > /dev/null; then
    echo "✅ Backend is responding"
else
    echo "❌ Backend is not responding"
fi

# Test frontend
echo "🌐 Testing frontend..."
if curl -s http://localhost:8080 > /dev/null; then
    echo "✅ Frontend is responding"
else
    echo "❌ Frontend is not responding"
fi

# Test mobile compatibility
echo "📱 Testing mobile compatibility..."
USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"
if curl -s -H "User-Agent: $USER_AGENT" http://localhost:8080 > /dev/null; then
    echo "✅ Mobile compatibility confirmed"
else
    echo "❌ Mobile compatibility issues detected"
fi

echo ""
echo "🎉 Deployment test completed!"
echo "Your app should be accessible at: http://localhost:8080"
