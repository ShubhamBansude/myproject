#!/bin/bash

# Deploy to Render - Helper Script
echo "🚀 Waste Detection App - Render Deployment Helper"
echo "================================================="

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "❌ Git repository not initialized. Please run:"
    echo "   git init"
    echo "   git add ."
    echo "   git commit -m 'Initial commit'"
    echo "   git remote add origin <your-github-repo-url>"
    echo "   git push -u origin main"
    exit 1
fi

# Check if we're on the right branch
current_branch=$(git branch --show-current)
echo "📍 Current branch: $current_branch"

if [ "$current_branch" != "cursor/deploy-website-to-render-981a" ]; then
    echo "⚠️  You're not on the deployment branch. Consider switching to:"
    echo "   git checkout cursor/deploy-website-to-render-981a"
fi

# Check if files exist
echo "🔍 Checking deployment files..."

files_to_check=("render.yaml" "Procfile" "backend/Procfile" "backend/requirements.txt" ".env.example")
for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file exists"
    else
        echo "❌ $file missing"
    fi
done

echo ""
echo "📋 Next Steps:"
echo "1. Push your code to GitHub:"
echo "   git add ."
echo "   git commit -m 'Add Render deployment configuration'"
echo "   git push origin $current_branch"
echo ""
echo "2. Go to https://render.com and:"
echo "   - Sign up/Login"
echo "   - Click 'New' → 'Blueprint'"
echo "   - Connect your GitHub repository"
echo "   - Select this repository and branch"
echo "   - Click 'Apply' to deploy"
echo ""
echo "3. Set environment variables in Render dashboard:"
echo "   - FLASK_ENV=production"
echo "   - FLASK_APP=app.py"
echo "   - PORT=10000"
echo "   - (Optional) GEMINI_API_KEY=your_key_here"
echo ""
echo "4. After deployment, update your frontend API URLs to use the Render backend URL"
echo ""
echo "📖 For detailed instructions, see RENDER_DEPLOYMENT.md"
echo ""
echo "🎉 Happy deploying!"