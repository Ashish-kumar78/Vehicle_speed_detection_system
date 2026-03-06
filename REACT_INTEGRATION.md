# React.js Frontend Integration Guide ⚛️

This guide shows you how to integrate React.js with the existing backend (Django + Streamlit) for a modern, production-ready frontend.

## Why React? 🤔

**Current Streamlit Approach:**
- ✅ Quick to develop and deploy
- ✅ Python-only codebase
- ✅ Perfect for B.Tech projects
- ❌ Limited customization
- ❌ Less modern UI/UX

**React Approach:**
- ✅ Modern, responsive UI
- ✅ Component-based architecture
- ✅ Better state management
- ✅ Production-ready
- ✅ Showcases full-stack skills
- ❌ Requires API development
- ❌ More complex setup

---

## Approach 1: Hybrid (Recommended for B.Tech) 🎯

Keep Streamlit as-is and add React components gradually. This gives you the best of both worlds.

### Step 1: Add Django REST Framework

```bash
cd vehicle_monitoring
pip install djangorestframework django-cors-headers
```

### Step 2: Update Django Settings (`vehicle_monitoring/settings.py`)

```python
INSTALLED_APPS = [
    # ... existing apps
    'rest_framework',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Add at top
    # ... existing middleware
]

# Allow CORS from React app
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]

# REST Framework config
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny'
    ]
}
```

### Step 3: Create API Endpoints

Create `vehicle_monitoring/detection/api_views.py`:

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import VehicleRecord, SystemSettings
from .serializers import VehicleRecordSerializer, SystemSettingsSerializer
from django.db.models import Count

@api_view(['GET'])
def get_vehicle_records(request):
    """Get all vehicle records with optional filtering"""
    vehicle_number = request.GET.get('vehicle_number')
    
    if vehicle_number:
        records = VehicleRecord.objects.filter(
            vehicle_number__icontains=vehicle_number
        ).order_by('-timestamp')[:100]
    else:
        records = VehicleRecord.objects.all().order_by('-timestamp')[:100]
    
    serializer = VehicleRecordSerializer(records, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_dashboard_stats(request):
    """Get dashboard statistics"""
    total = VehicleRecord.objects.count()
    overspeed = VehicleRecord.objects.filter(status='overspeed').count()
    normal = VehicleRecord.objects.filter(status='normal').count()
    blocked = VehicleRecord.objects.filter(violation_count__gte=3).count()
    
    return Response({
        'total_vehicles': total,
        'overspeed_violations': overspeed,
        'normal_vehicles': normal,
        'blocked_licenses': blocked,
        'compliance_rate': (normal / total * 100) if total > 0 else 0
    })

@api_view(['GET', 'PUT'])
def get_settings(request):
    """Get or update system settings"""
    settings = SystemSettings.objects.first()
    
    if request.method == 'GET':
        serializer = SystemSettingsSerializer(settings)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = SystemSettingsSerializer(settings, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
```

### Step 4: Create Serializers

Create `vehicle_monitoring/detection/serializers.py`:

```python
from rest_framework import serializers
from .models import VehicleRecord, SystemSettings

class VehicleRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleRecord
        fields = '__all__'

class SystemSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSettings
        fields = '__all__'
```

### Step 5: Add API URLs

Update `vehicle_monitoring/urls.py`:

```python
from django.urls import path, include
from detection.api_views import get_vehicle_records, get_dashboard_stats, get_settings

urlpatterns = [
    # ... existing URLs
    path('api/records/', get_vehicle_records),
    path('api/stats/', get_dashboard_stats),
    path('api/settings/', get_settings),
]
```

---

## Approach 2: Full React Frontend 🚀

Build a complete React app to replace Streamlit entirely.

### Step 1: Create React App

```bash
npx create-react-app frontend
cd frontend
npm install axios react-router-dom @mui/material @emotion/react @emotion/styled
```

### Step 2: Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Dashboard.jsx
│   │   ├── LiveCamera.jsx
│   │   ├── VideoUpload.jsx
│   │   ├── RecordsTable.jsx
│   │   └── AdminPanel.jsx
│   ├── services/
│   │   └── api.js
│   ├── App.js
│   └── index.js
```

### Step 3: API Service (`src/services/api.js`)

```javascript
import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8000/api';

export const api = {
  getStats: () => axios.get(`${API_BASE}/stats/`),
  getRecords: (searchTerm) => axios.get(`${API_BASE}/records/?vehicle_number=${searchTerm}`),
  getSettings: () => axios.get(`${API_BASE}/settings/`),
  updateSettings: (data) => axios.put(`${API_BASE}/settings/`, data),
};
```

### Step 4: Dashboard Component (`src/components/Dashboard.jsx`)

```jsx
import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Card, Grid, Typography, Box } from '@mui/material';

function Dashboard() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.getStats().then(response => setStats(response.data));
  }, []);

  if (!stats) return <div>Loading...</div>;

  return (
    <Box sx={{ flexGrow: 1, p: 3 }}>
      <Typography variant="h4" gutterBottom>
        📊 Vehicle Speed Detection Dashboard
      </Typography>
      
      <Grid container spacing={3}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ p: 3, bgcolor: '#667eea', color: 'white' }}>
            <Typography variant="h6">🚗 Total Vehicles</Typography>
            <Typography variant="h3">{stats.total_vehicles}</Typography>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ p: 3, bgcolor: '#f56565', color: 'white' }}>
            <Typography variant="h6">⚠️ Overspeed Violations</Typography>
            <Typography variant="h3">{stats.overspeed_violations}</Typography>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ p: 3, bgcolor: '#ed8936', color: 'white' }}>
            <Typography variant="h6">🚫 Blocked Licenses</Typography>
            <Typography variant="h3">{stats.blocked_licenses}</Typography>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ p: 3, bgcolor: '#48bb78', color: 'white' }}>
            <Typography variant="h6">✅ Normal Vehicles</Typography>
            <Typography variant="h3">{stats.normal_vehicles}</Typography>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}

export default Dashboard;
```

### Step 5: Main App (`src/App.js`)

```jsx
import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import LiveCamera from './components/LiveCamera';
import VideoUpload from './components/VideoUpload';
import RecordsTable from './components/RecordsTable';
import AdminPanel from './components/AdminPanel';

function App() {
  return (
    <BrowserRouter>
      <div className="App">
        <nav style={{ padding: '20px', background: '#667eea', color: 'white' }}>
          <Link to="/" style={{ marginRight: '20px', color: 'white' }}>Dashboard</Link>
          <Link to="/live" style={{ marginRight: '20px', color: 'white' }}>Live Camera</Link>
          <Link to="/upload" style={{ marginRight: '20px', color: 'white' }}>Video Upload</Link>
          <Link to="/records" style={{ marginRight: '20px', color: 'white' }}>Records</Link>
          <Link to="/admin" style={{ color: 'white' }}>Admin</Link>
        </nav>
        
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/live" element={<LiveCamera />} />
          <Route path="/upload" element={<VideoUpload />} />
          <Route path="/records" element={<RecordsTable />} />
          <Route path="/admin" element={<AdminPanel />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
```

### Step 6: Run Both Servers

Terminal 1 - Django Backend:
```bash
cd vehicle_monitoring
python manage.py runserver
```

Terminal 2 - React Frontend:
```bash
cd frontend
npm start
```

Visit: `http://localhost:3000`

---

## Deployment Options 🚀

### Option 1: Separate Deployment
- **Frontend**: Vercel, Netlify
- **Backend**: Heroku, Railway, AWS
- **Database**: MySQL on cloud

### Option 2: Serve React via Django
```bash
# Build React app
npm run build

# Copy build folder to Django static files
cp -r build/* ../vehicle_monitoring/static/
```

Configure Django to serve React:
```python
# settings.py
STATICFILES_DIRS = [BASE_DIR / "static"]

# urls.py
from django.views.static import serve
urlpatterns += [
    path('', serve, {'document_root': STATIC_ROOT}),
]
```

---

## Which Approach Should You Choose? 🤷

**Use Hybrid (Approach 1) if:**
- ✅ Working on B.Tech project
- ✅ Short on time
- ✅ Want quick results
- ✅ Need both working demos

**Use Full React (Approach 2) if:**
- ✅ Building production app
- ✅ Want to showcase React skills
- ✅ Have deployment plans
- ✅ Need highly customized UI

---

## Additional Features to Add 💡

1. **WebSocket for Live Streaming**
   ```bash
   npm install socket.io-client
   ```

2. **Charts & Graphs**
   ```bash
   npm install recharts chart.js react-chartjs-2
   ```

3. **State Management**
   ```bash
   npm install @reduxjs/toolkit react-redux
   ```

4. **Better UI Components**
   ```bash
   npm install @chakra-ui/react
   # or
   npm install tailwindcss
   ```

---

## Need Help? 🆘

Common issues and solutions:

### CORS Errors
```python
# In Django settings.py
CORS_ALLOW_ALL_ORIGINS = True  # Development only
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
```

### API Not Responding
- Check Django server is running
- Verify API endpoints in browser: `http://localhost:8000/api/stats/`
- Check CORS configuration

### Build Issues
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

---

## Conclusion 🎉

You now have two paths:
1. **Keep enhanced Streamlit** (current implementation) - Perfect for B.Tech!
2. **Add React frontend** when ready for production

The hybrid approach lets you demo quickly while keeping the React option open for future enhancement.

Good luck with your project! 🚀
