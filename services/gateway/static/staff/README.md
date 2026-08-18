# AI Platform - User Self-Serve Portal

## Overview

Hoàn chỉnh staff dashboard cho AI Platform với các tính năng:

- ✅ **Topbar**: Search, Notifications, User Profile
- ✅ **Sidebar**: Navigation menu với sections (Dashboard, Users, Services, Billing, Admin)
- ✅ **Dashboard**: KPI cards, Recent Activity, Pending Approvals
- ✅ **Users Management**: User listing, status filters, actions
- ✅ **Responsive**: Mobile-friendly layout

## File Structure

```
services/gateway/static/staff/
├── dashboard-complete.html      # Main dashboard page (hoàn chỉnh)
├── users.html                    # Users management page
├── services.html                 # Services listing (TODO)
├── billing.html                  # Billing/Payments (TODO)
├── settings.html                 # Admin Settings (TODO)
├── css/
│   └── layout.css               # Shared CSS (optional)
└── js/
    └── layout.js                # Shared JS (optional)
```

## Dashboard Components

### 1. Topbar (64px height)

- Brand logo
- Search bar
- Notifications with badge
- User profile dropdown
- Links to settings/logout

### 2. Sidebar (220px width)

- Navigation sections:
  - Dashboard (Overview, Analytics)
  - Users (All Users, Active, Inactive)
  - Services (Services listing, Status filters)
  - Billing (Payments, Subscriptions, Invoices)
  - Admin (System Health, Logs, Settings)
- User profile section at bottom
- Logout button

### 3. Main Content Area

- Page header with title
- Filter/action buttons
- KPI cards grid
- Data tables with status badges
- Pagination (optional)

## Color Scheme

| Component   | Color   | Usage                |
| ----------- | ------- | -------------------- |
| Primary     | #0f172a | Text, headings       |
| Primary-500 | #3b82f6 | Links, active states |
| Primary-600 | #2563eb | Hover states         |
| Success     | #10b981 | Positive status      |
| Warning     | #f59e0b | Pending status       |
| Danger      | #ef4444 | Error, alerts        |
| Background  | #f8fafc | Page background      |
| White       | #ffffff | Cards, components    |
| Border      | #e2e8f0 | Dividers             |
| Text Light  | #64748b | Secondary text       |

## Status Badges

```html
<span class="status-badge success">Active</span>
<span class="status-badge warning">Pending</span>
<span class="status-badge error">Failed</span>
<span class="status-badge pending">Pending Approval</span>
```

## KPI Card Example

```html
<div class="kpi-card">
  <div class="kpi-label">Total Users</div>
  <div class="kpi-value">1,245</div>
  <div class="kpi-change positive">
    <i class="fas fa-arrow-up"></i> +12% from last week
  </div>
</div>
```

## Table Example

```html
<div class="card">
  <div class="card-header">
    <div class="card-title">Recent Activity</div>
    <a href="#" class="action-btn">View All</a>
  </div>
  <div class="card-body">
    <table>
      <thead>
        <tr>
          <th>Column 1</th>
          <th>Column 2</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Data 1</td>
          <td>Data 2</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
```

## Integration with FastAPI

### Serve Dashboard

```python
@app.get("/staff/dashboard", include_in_schema=False)
async def serve_staff_dashboard():
    dashboard_path = os.path.join(current_dir, "static", "staff", "dashboard-complete.html")
    return FileResponse(dashboard_path, media_type="text/html")

@app.get("/staff/users", include_in_schema=False)
async def serve_staff_users():
    users_path = os.path.join(current_dir, "static", "staff", "users.html")
    return FileResponse(users_path, media_type="text/html")
```

### API Endpoints for Dashboard

```bash
GET /api/v1/dashboard/stats
GET /api/v1/dashboard/activity
GET /api/v1/users?page=1&limit=20
GET /api/v1/jobs?status=active
GET /api/v1/billing/payments
```

## Features to Implement

- [ ] User authentication & session management
- [ ] Real-time notifications
- [ ] Advanced search filters
- [ ] Data export (CSV, PDF)
- [ ] Dark mode toggle
- [ ] Mobile sidebar toggle
- [ ] User preferences storage
- [ ] Audit logs
- [ ] API rate limit visualization
- [ ] System health monitoring

## Security Considerations

1. ✅ All staff dashboard pages should require authentication
2. ✅ Implement role-based access control (RBAC)
3. ✅ Add CSRF protection for forms
4. ✅ Validate all user inputs
5. ✅ Sanitize displayed data
6. ✅ Use secure HTTP headers

## Responsive Design

- **Desktop**: Full sidebar (220px) + main content
- **Tablet (1024px)**: Reduced sidebar (180px)
- **Mobile (768px)**: Collapsible sidebar with toggle

## Performance Tips

1. Lazy load tables with pagination
2. Cache API responses client-side
3. Minimize CSS/JS bundle size
4. Use CDN for Font Awesome
5. Implement virtual scrolling for large lists

## Next Steps

1. Connect frontend to FastAPI backend
2. Implement user authentication
3. Build API endpoints for each dashboard section
4. Add real-time WebSocket updates
5. Create mobile app version
6. Add analytics tracking

---

**Created**: 2026-08-18  
**Status**: ✅ Initial Dashboard Complete  
**Template**: Minimalist SaaS Design
