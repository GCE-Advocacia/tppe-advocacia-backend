from fastapi import APIRouter

from app.modules.appointments.router import router as appointments_router
from app.modules.articles.router import router as articles_router
from app.modules.audit_logs.router import router as audit_logs_router
from app.modules.auth.router import router as auth_router
from app.modules.clients.router import router as clients_router
from app.modules.datajud.router import router as datajud_router
from app.modules.deadlines.router import router as deadlines_router
from app.modules.external_api_logs.router import router as external_api_logs_router
from app.modules.finance.router import router as finance_router
from app.modules.forensic_holidays.router import router as forensic_holidays_router
from app.modules.google_calendar.router import router as google_calendar_router
from app.modules.health.router import router as health_router
from app.modules.leads.router import router as leads_router
from app.modules.media.router import router as media_router
from app.modules.notifications.router import router as notifications_router
from app.modules.office_config.router import router as office_config_router
from app.modules.processes.router import router as processes_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(leads_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(audit_logs_router)
api_router.include_router(office_config_router)
api_router.include_router(media_router)
api_router.include_router(articles_router)
api_router.include_router(clients_router)
api_router.include_router(processes_router)
api_router.include_router(datajud_router)
api_router.include_router(external_api_logs_router)
api_router.include_router(notifications_router)
api_router.include_router(tasks_router)
api_router.include_router(forensic_holidays_router)
api_router.include_router(deadlines_router)
api_router.include_router(appointments_router)
api_router.include_router(google_calendar_router)
api_router.include_router(finance_router)
