from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server.database import SessionLocal
from server.models import (
    AttendanceSession,
    Customer,
    Employee,
    Membership,
    Person,
    PtEnrollment,
    PtEnrollmentCoach,
    ServicePackage,
)
from server.timeutils import utc_now, vietnam_today


CUSTOMER_CODE = "CUS-DEMO-PT-Q"
COACH_CODE = "EMP-DEMO-PT-Q"


def _get_or_create_person(db, phone: str, name: str) -> Person:
    person = db.query(Person).filter(Person.phone == phone).first()
    if person:
        person.display_name = name
        person.status = "active"
        return person
    person = Person(display_name=name, phone=phone, status="active")
    db.add(person)
    db.flush()
    return person


def main() -> int:
    db = SessionLocal()
    try:
        today = vietnam_today()
        member_person = _get_or_create_person(db, "0909990001", "Demo PT Cho Xu Ly")
        member = db.query(Customer).filter(Customer.customer_code == CUSTOMER_CODE).first()
        if not member:
            member = Customer(
                person_id=member_person.id,
                customer_code=CUSTOMER_CODE,
                status="active",
                source="Demo",
            )
            db.add(member)
            db.flush()
        else:
            member.person_id = member_person.id
            member.status = "active"

        coach_person = _get_or_create_person(db, "0909990002", "Coach Demo")
        coach = db.query(Employee).filter(Employee.employee_code == COACH_CODE).first()
        if not coach:
            coach = Employee(
                person_id=coach_person.id,
                employee_code=COACH_CODE,
                job_title="Coach",
                status="active",
            )
            db.add(coach)
            db.flush()
        else:
            coach.person_id = coach_person.id
            coach.job_title = "Coach"
            coach.status = "active"

        gym_plan = db.query(ServicePackage).filter(ServicePackage.code == "DEMO-GYM-30").first()
        if not gym_plan:
            gym_plan = ServicePackage(
                code="DEMO-GYM-30",
                name="Demo Gym 30 ngay",
                category="Fitness",
                duration_days=30,
                price=300000,
                is_pt=False,
                is_active=True,
            )
            db.add(gym_plan)
            db.flush()
        else:
            gym_plan.name = "Demo Gym 30 ngay"
            gym_plan.duration_days = 30
            gym_plan.price = 300000
            gym_plan.is_active = True

        membership = db.query(Membership).filter(Membership.code == "MS-DEMO-PT-Q").first()
        if not membership:
            membership = Membership(
                customer_id=member.id,
                package_id=gym_plan.id,
                code="MS-DEMO-PT-Q",
                registered_at=today,
                starts_at=today - timedelta(days=3),
                expires_at=today + timedelta(days=27),
                activated_at=today - timedelta(days=3),
                final_price=300000,
                paid_amount=300000,
                status="active",
            )
            db.add(membership)
        else:
            membership.customer_id = member.id
            membership.package_id = gym_plan.id
            membership.starts_at = today - timedelta(days=3)
            membership.expires_at = today + timedelta(days=27)
            membership.activated_at = today - timedelta(days=3)
            membership.status = "active"

        enrollment = (
            db.query(PtEnrollment)
            .filter(PtEnrollment.customer_id == member.id)
            .order_by(PtEnrollment.id)
            .first()
        )
        if not enrollment:
            enrollment = PtEnrollment(
                customer_id=member.id,
                coach_id=coach.id,
                package_name="Demo PT 10 buoi",
                group_type="1:1",
                starts_at=today - timedelta(days=3),
                expires_at=today + timedelta(days=27),
                total_sessions=10,
                remaining_sessions=8,
                schedule_json="",
                final_price=1500000,
                paid_amount=1500000,
                debt_amount=0,
                status="active",
            )
            db.add(enrollment)
            db.flush()
        else:
            enrollment.coach_id = coach.id
            enrollment.package_name = "Demo PT 10 buoi"
            enrollment.group_type = "1:1"
            enrollment.starts_at = today - timedelta(days=3)
            enrollment.expires_at = today + timedelta(days=27)
            enrollment.total_sessions = max(enrollment.total_sessions or 10, 10)
            enrollment.remaining_sessions = max(enrollment.remaining_sessions or 0, 8)
            enrollment.status = "active"

        assignment = (
            db.query(PtEnrollmentCoach)
            .filter(PtEnrollmentCoach.enrollment_id == enrollment.id, PtEnrollmentCoach.coach_id == coach.id)
            .first()
        )
        if not assignment:
            db.add(PtEnrollmentCoach(enrollment_id=enrollment.id, coach_id=coach.id))

        session = (
            db.query(AttendanceSession)
            .filter(
                AttendanceSession.customer_id == member.id,
                AttendanceSession.source == "manual",
                AttendanceSession.processed_at.is_(None),
            )
            .order_by(AttendanceSession.id.desc())
            .first()
        )
        if not session:
            session = AttendanceSession(
                customer_id=member.id,
                checked_in_at=utc_now(),
                source="manual",
                result="allowed",
                status="open",
            )
            db.add(session)
            db.flush()
        else:
            session.checked_in_at = utc_now()
            session.checked_out_at = None
            session.status = "open"
            session.workout_type = None
            session.pt_enrollment_id = None
            session.processed_at = None
            session.processed_by_user_id = None

        db.commit()
        print(f"Seeded member-processing demo: member={CUSTOMER_CODE}, sessionId={session.id}, ptEnrollmentId={enrollment.id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
