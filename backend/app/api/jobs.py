"""Job & company search with seeded sample data."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.job import Company, Job
from app.models.user import User

router = APIRouter(prefix="/jobs", tags=["jobs"])

SAMPLE_COMPANIES = [
    {"name": "Google", "slug": "google", "description": "Search, cloud, AI and more", "tech_stack": ["Python", "Go", "Kubernetes", "TensorFlow"], "website": "https://google.com"},
    {"name": "Microsoft", "slug": "microsoft", "description": "Software, cloud, productivity", "tech_stack": ["C#", "Azure", "TypeScript", ".NET"], "website": "https://microsoft.com"},
    {"name": "Amazon", "slug": "amazon", "description": "E-commerce, cloud, technology", "tech_stack": ["Java", "AWS", "Python", "DynamoDB"], "website": "https://amazon.com"},
    {"name": "Meta", "slug": "meta", "description": "Social media, VR, AI", "tech_stack": ["React", "Python", "PyTorch", "GraphQL"], "website": "https://meta.com"},
    {"name": "Netflix", "slug": "netflix", "description": "Streaming, entertainment, tech", "tech_stack": ["Java", "Node.js", "AWS", "Cassandra"], "website": "https://netflix.com"},
    {"name": "Adobe", "slug": "adobe", "description": "Creativity, multimedia, digital marketing", "tech_stack": ["JavaScript", "C++", "React", "AWS"], "website": "https://adobe.com"},
]

SAMPLE_JOBS = [
    {"title": "Software Engineer", "location": "Bengaluru, India", "employment_type": "Full-time", "seniority": "Mid level", "company_slug": "google", "description": "Build scalable systems that power millions of users. Work with a team of engineers, designers and product managers."},
    {"title": "Software Engineer", "location": "Hyderabad, India", "employment_type": "Full-time", "seniority": "Mid level", "company_slug": "microsoft", "description": "Design and build cloud services on Azure. Collaborate across teams to deliver reliable products."},
    {"title": "SDE II", "location": "Remote", "employment_type": "Full-time", "seniority": "Mid level", "company_slug": "amazon", "description": "Own services end-to-end. Work on high-scale distributed systems and customer-facing features."},
    {"title": "Frontend Engineer", "location": "Remote", "employment_type": "Full-time", "seniority": "Mid level", "company_slug": "netflix", "description": "Build delightful streaming experiences with React and modern web tech."},
    {"title": "Backend Engineer", "location": "Bengaluru, India", "employment_type": "Full-time", "seniority": "Senior", "company_slug": "meta", "description": "Scale social infrastructure. Focus on performance, reliability and developer experience."},
    {"title": "Full Stack Engineer", "location": "Noida, India", "employment_type": "Full-time", "seniority": "Mid level", "company_slug": "adobe", "description": "Ship creative tools used by millions. TypeScript, React, and cloud services."},
]


class CompanyOut(BaseModel):
    id: int
    name: str
    slug: Optional[str]
    description: Optional[str]
    tech_stack: Optional[list]
    website: Optional[str]

    class Config:
        from_attributes = True


class JobOut(BaseModel):
    id: int
    title: str
    location: Optional[str]
    employment_type: Optional[str]
    seniority: Optional[str]
    description: Optional[str]
    company: Optional[CompanyOut] = None

    class Config:
        from_attributes = True


async def ensure_seed_data(db: AsyncSession) -> None:
    existing = await db.scalar(select(Company.id).limit(1))
    if existing:
        return
    slug_to_id: dict[str, int] = {}
    for c in SAMPLE_COMPANIES:
        company = Company(
            name=c["name"],
            slug=c["slug"],
            description=c["description"],
            tech_stack=c["tech_stack"],
            website=c["website"],
        )
        db.add(company)
        await db.flush()
        slug_to_id[c["slug"]] = company.id
    for j in SAMPLE_JOBS:
        job = Job(
            title=j["title"],
            location=j["location"],
            employment_type=j["employment_type"],
            seniority=j["seniority"],
            description=j["description"],
            raw_jd_text=j["description"],
            company_id=slug_to_id.get(j["company_slug"]),
        )
        db.add(job)
    await db.flush()


@router.get("/companies", response_model=List[CompanyOut])
async def list_companies(
    q: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_seed_data(db)
    stmt = select(Company).order_by(Company.name)
    if q:
        stmt = stmt.where(
            or_(Company.name.ilike(f"%{q}%"), Company.description.ilike(f"%{q}%"))
        )
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    company = await db.get(Company, company_id)
    if not company:
        from fastapi import HTTPException
        raise HTTPException(404, "Company not found")
    return company


@router.get("", response_model=List[JobOut])
async def list_jobs(
    q: Optional[str] = Query(None),
    location: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_seed_data(db)
    stmt = select(Job).options(selectinload(Job.company)).order_by(Job.id.desc())
    if q:
        stmt = stmt.where(
            or_(Job.title.ilike(f"%{q}%"), Job.description.ilike(f"%{q}%"))
        )
    if location:
        stmt = stmt.where(Job.location.ilike(f"%{location}%"))
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).options(selectinload(Job.company)).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        from fastapi import HTTPException
        raise HTTPException(404, "Job not found")
    return job
