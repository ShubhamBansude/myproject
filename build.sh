#!/bin/bash

# Build script for Render deployment
echo "Starting build process..."

# Install frontend dependencies and build
echo "Building frontend..."
cd frontend
npm ci
npm run build
cd ..

# Install backend dependencies
echo "Installing backend dependencies..."
cd backend
pip install -r requirements.txt
cd ..

echo "Build completed successfully!"