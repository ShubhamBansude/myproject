#!/bin/bash

# Waste Rewards App Deployment Script
# This script deploys the app using Docker Compose

set -e

echo "🚀 Starting Waste Rewards App Deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration before running again."
    echo "   Especially set your GEMINI_API_KEY if you want AI features."
    exit 0
fi

# Build and start the services
echo "🔨 Building Docker images..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check if services are running
echo "🔍 Checking service status..."
docker-compose ps

# Get the public IP or localhost
if command -v curl &> /dev/null; then
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "localhost")
else
    PUBLIC_IP="localhost"
fi

echo ""
echo "✅ Deployment completed successfully!"
echo ""
echo "🌐 Your app is now accessible at:"
echo "   Local: http://localhost:8080"
echo "   Public: http://$PUBLIC_IP:8080"
echo ""
echo "📱 Mobile users can access your app at:"
echo "   http://$PUBLIC_IP:8080"
echo ""
echo "🔧 To manage your deployment:"
echo "   View logs: docker-compose logs -f"
echo "   Stop app: docker-compose down"
echo "   Restart: docker-compose restart"
echo "   Update: docker-compose pull && docker-compose up -d"
echo ""
echo "📊 Service endpoints:"
echo "   Frontend: http://$PUBLIC_IP:8080"
echo "   Backend API: http://$PUBLIC_IP:8080/api/"
echo "   Health Check: http://$PUBLIC_IP:8080/api/stats"
echo ""
echo "🎉 Share this link with your friends: http://$PUBLIC_IP:8080"
