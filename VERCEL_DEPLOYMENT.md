# Deploying EDRMS to Vercel (Step-by-Step Guide)

This guide walks you through deploying the **Eksper EDRMS Frontend** to **Vercel** connected directly to your GitHub repository.

---

## 1. Prerequisites

1. Your repository is pushed to GitHub: [https://github.com/Satyanand-1/Eksper-Doc-Digitalization](https://github.com/Satyanand-1/Eksper-Doc-Digitalization)
2. A free [Vercel account](https://vercel.com) connected to your GitHub account.
3. Your backend API URL (e.g. deployed on Render, Railway, Fly.io, AWS, or an accessible domain).

---

## 2. Deploying on Vercel

### Step 1: Import Project in Vercel
1. Log in to your [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **"Add New..."** $\rightarrow$ **"Project"**.
3. Under **"Import Git Repository"**, find and select **`Eksper-Doc-Digitalization`**.

### Step 2: Configure Project Settings (Important!)
Because this repository is a full-stack monorepo (`frontend/` and `backend/`), configure the project settings before clicking deploy:

1. **Framework Preset**: Select **Next.js** (automatically detected).
2. **Root Directory**:
   - Click **"Edit"** next to *Root Directory*.
   - Select or type **`frontend`** $\rightarrow$ Click **"Continue"**.
3. **Build and Output Settings**:
   - Leave default (`npm run build` / `.next`).
4. **Environment Variables**:
   - Expand the **"Environment Variables"** section.
   - Add the key:
     ```
     NEXT_PUBLIC_API_URL
     ```
   - Value: URL of your deployed FastAPI backend (e.g., `https://your-backend-api.onrender.com` or `https://api.yourdomain.com`).
   *(Note: Do not add a trailing slash)*.

### Step 3: Deploy
1. Click **"Deploy"**.
2. Vercel will install dependencies and build the Next.js production bundle.
3. Once finished, you will receive a live URL (e.g., `https://eksper-doc-digitalization.vercel.app`).

---

## 3. Continuous Deployment (CI/CD)
Whenever you push changes to your `main` branch on GitHub:
```bash
git add .
git commit -m "Your update message"
git push origin main
```
Vercel will automatically build and deploy the update in real-time.
