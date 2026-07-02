from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.modules.appointments.model import Appointment, AppointmentType


class AppointmentRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _query(self):
        return select(Appointment).options(joinedload(Appointment.creator))

    def get_by_id(self, appointment_id: int) -> Appointment | None:
        return self.db.scalars(
            self._query().where(Appointment.id == appointment_id)
        ).first()

    def get_by_google_event_id(
        self, google_event_id: str, created_by: int
    ) -> Appointment | None:
        """Compromisso do usuário vinculado a um evento do Google.

        Escopado por `created_by`: `google_event_id` é único por calendário
        (por usuário), então dois usuários não colidem.
        """
        return self.db.scalars(
            self._query().where(
                Appointment.google_event_id == google_event_id,
                Appointment.created_by == created_by,
            )
        ).first()

    def create(
        self,
        title: str,
        type: AppointmentType,
        starts_at: datetime,
        duration_minutes: int,
        description: str | None,
        location: str | None,
        client_id: int | None,
        process_id: int | None,
        created_by: int,
    ) -> Appointment:
        appointment = Appointment(
            title=title,
            type=type,
            starts_at=starts_at,
            duration_minutes=duration_minutes,
            description=description,
            location=location,
            client_id=client_id,
            process_id=process_id,
            created_by=created_by,
        )
        self.db.add(appointment)
        self.db.flush()
        return self.get_by_id(appointment.id)

    def create_from_google(
        self,
        created_by: int,
        google_event_id: str,
        title: str,
        type: AppointmentType,
        starts_at: datetime,
        duration_minutes: int,
        description: str | None,
        location: str | None,
    ) -> Appointment:
        """Cria um compromisso importado do Google Calendar.

        Já nasce com `is_synced_to_google=True` e `google_event_id` setado, o
        que impede o AppointmentService de reenviá-lo pro Google (anti-loop).
        """
        appointment = Appointment(
            title=title,
            type=type,
            starts_at=starts_at,
            duration_minutes=duration_minutes,
            description=description,
            location=location,
            created_by=created_by,
            google_event_id=google_event_id,
            is_synced_to_google=True,
        )
        self.db.add(appointment)
        self.db.flush()
        return self.get_by_id(appointment.id)

    def update(self, appointment: Appointment, data: dict) -> Appointment:
        for key, value in data.items():
            setattr(appointment, key, value)
        self.db.flush()
        return self.get_by_id(appointment.id)

    def delete(self, appointment: Appointment) -> None:
        self.db.delete(appointment)
        self.db.flush()

    def list(
        self,
        created_by: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        type: AppointmentType | None = None,
        client_id: int | None = None,
        process_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Appointment], int]:
        base = select(Appointment).where(Appointment.created_by == created_by)

        if date_from is not None:
            base = base.where(Appointment.starts_at >= date_from)
        if date_to is not None:
            base = base.where(Appointment.starts_at <= date_to)
        if type is not None:
            base = base.where(Appointment.type == type)
        if client_id is not None:
            base = base.where(Appointment.client_id == client_id)
        if process_id is not None:
            base = base.where(Appointment.process_id == process_id)

        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        items = list(
            self.db.scalars(
                base.options(joinedload(Appointment.creator))
                .order_by(Appointment.starts_at.asc(), Appointment.id.asc())
                .offset((page - 1) * limit)
                .limit(limit)
            ).all()
        )
        return items, total

    def list_unsynced_future(self, created_by: int, now: datetime) -> list[Appointment]:
        """Compromissos futuros do usuário ainda não sincronizados ao Google.

        Usado pelo sync retroativo (`sync-all`). O filtro por
        `is_synced_to_google` é o que torna a operação idempotente.
        """
        return list(
            self.db.scalars(
                select(Appointment)
                .options(joinedload(Appointment.creator))
                .where(
                    Appointment.created_by == created_by,
                    Appointment.is_synced_to_google.is_(False),
                    Appointment.starts_at >= now,
                )
                .order_by(Appointment.starts_at.asc(), Appointment.id.asc())
            ).all()
        )
