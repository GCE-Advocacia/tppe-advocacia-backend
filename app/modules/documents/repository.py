from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.modules.documents.model import ProcessDocument


class ProcessDocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _query(self):
        return select(ProcessDocument).options(joinedload(ProcessDocument.uploader))

    def create(
        self,
        *,
        process_id: int,
        original_name: str,
        stored_name: str,
        mime_type: str,
        size_bytes: int,
        uploaded_by: int,
    ) -> ProcessDocument:
        document = ProcessDocument(
            process_id=process_id,
            original_name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            uploaded_by=uploaded_by,
        )
        self.db.add(document)
        self.db.flush()
        return self.db.scalars(
            self._query().where(ProcessDocument.id == document.id)
        ).first()

    def get_by_id(self, document_id: int, process_id: int) -> ProcessDocument | None:
        return self.db.scalars(
            self._query().where(
                ProcessDocument.id == document_id,
                ProcessDocument.process_id == process_id,
            )
        ).first()

    def list_by_process(
        self, process_id: int, page: int = 1, limit: int = 20
    ) -> tuple[list[ProcessDocument], int]:
        base = select(ProcessDocument).where(ProcessDocument.process_id == process_id)
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        documents = list(
            self.db.scalars(
                self._query()
                .where(ProcessDocument.process_id == process_id)
                .order_by(ProcessDocument.created_at.desc(), ProcessDocument.id.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
            .unique()
            .all()
        )
        return documents, total

    def delete(self, document: ProcessDocument) -> None:
        self.db.delete(document)
        self.db.flush()
