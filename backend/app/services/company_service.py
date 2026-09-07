from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.schemas.company import CompanyUpdate


class CompanyService:
    @staticmethod
    def get(db: Session) -> Company | None:
        return db.scalar(
            select(Company).limit(1)
        )

    @staticmethod
    def update(
        db: Session,
        data: CompanyUpdate,
    ) -> Company:
        company = CompanyService.get(db)

        if company is None:
            company = Company(
                **data.model_dump()
            )

            db.add(company)

        else:
            for field, value in data.model_dump().items():
                setattr(company, field, value)

        db.commit()
        db.refresh(company)

        return company