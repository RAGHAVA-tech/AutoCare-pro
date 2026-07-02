"""
Automotive Service Booking AI Agent System
==========================================
Multi-framework AI agent architecture:
- CrewAI: Customer-facing conversational agent
- AutoGen: Appointment booking orchestration
- Semantic Kernel: CRM integration & intelligence
- Voice handling: Phone call simulation with TTS/STT
"""

import asyncio
import json
import uuid
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import Optional
from enum import Enum

# Optional DB persistence helpers (best-effort)
try:
    from db import (
        get_session, CustomerORM, AppointmentORM, serialize_history, deserialize_history,
        load_all_customers, load_all_appointments, update_appointment_status,
    )
except Exception:
    get_session = None
    CustomerORM = None
    AppointmentORM = None
    serialize_history = None
    deserialize_history = None
    load_all_customers = None
    load_all_appointments = None
    update_appointment_status = None
# ─── Data Models ────────────────────────────────────────────────────────────

class ServiceType(str, Enum):
    OIL_CHANGE       = "Oil Change"
    TIRE_ROTATION    = "Tire Rotation"
    BRAKE_INSPECTION = "Brake Inspection"
    ENGINE_TUNE      = "Engine Tune-Up"
    AC_SERVICE       = "A/C Service"
    TRANSMISSION     = "Transmission Service"
    FULL_INSPECTION  = "Full Vehicle Inspection"

class AppointmentStatus(str, Enum):
    PENDING   = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

@dataclass
class Customer:
    id: str
    name: str
    phone: str
    email: str
    vehicle_make: str
    vehicle_model: str
    vehicle_year: int
    service_history: list = field(default_factory=list)
    total_spent: float = 0.0
    preferred_advisor: Optional[str] = None
    loyalty_points: int = 0

@dataclass
class Appointment:
    id: str
    customer_id: str
    service_type: ServiceType
    scheduled_date: str
    scheduled_time: str
    status: AppointmentStatus
    advisor: str
    estimated_cost: float
    estimated_duration: int  # minutes
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

# ─── Mock CRM Database ───────────────────────────────────────────────────────

class CRMDatabase:
    """Simulates a CRM database with customer and appointment records."""
    
    def __init__(self):
        self.customers: dict[str, Customer] = {}
        self.appointments: dict[str, Appointment] = {}
        self.advisors = ["Mike Johnson", "Sarah Chen", "David Rodriguez", "Emily Park"]
        if not self._load_from_db():
            # No persisted data yet (fresh DB / DB unavailable) — seed demo data
            self._seed_data()

    def _load_from_db(self) -> bool:
        """Restore customers & appointments that were persisted in a previous
        run so bookings survive app restarts. Returns True if anything was
        loaded, False if the DB is empty/unavailable (caller should seed)."""
        if not (load_all_customers and load_all_appointments):
            return False
        try:
            db_customers = load_all_customers()
            db_appointments = load_all_appointments()
        except Exception as e:
            print("Warning: DB load failed, falling back to in-memory demo data:", e)
            return False

        if not db_customers:
            return False

        for c in db_customers:
            self.customers[c["id"]] = Customer(
                id=c["id"], name=c["name"], phone=c["phone"], email=c["email"],
                vehicle_make=c["vehicle_make"], vehicle_model=c["vehicle_model"],
                vehicle_year=c["vehicle_year"], service_history=c["service_history"],
                total_spent=c["total_spent"], preferred_advisor=c["preferred_advisor"],
                loyalty_points=c["loyalty_points"],
            )
        for a in db_appointments:
            try:
                service = ServiceType(a["service_type"])
            except ValueError:
                service = a["service_type"]
            try:
                status = AppointmentStatus(a["status"])
            except ValueError:
                status = AppointmentStatus.PENDING
            self.appointments[a["id"]] = Appointment(
                id=a["id"], customer_id=a["customer_id"], service_type=service,
                scheduled_date=a["scheduled_date"], scheduled_time=a["scheduled_time"],
                status=status, advisor=a["advisor"], estimated_cost=a["estimated_cost"],
                estimated_duration=a["estimated_duration"], notes=a["notes"],
            )
        print(f"✅ Restored {len(self.customers)} customers and {len(self.appointments)} "
              f"appointments from persistent storage.")
        return True

    def _seed_data(self):
        """Seed with sample customers."""
        sample_customers = [
            Customer("C001", "Rajesh Kumar", "+91-9876543210", "rajesh@email.com",
                     "Toyota", "Camry", 2019, 
                     ["Oil Change - 2024-01", "Tire Rotation - 2024-03"], 
                     4500.0, "Mike Johnson", 450),
            Customer("C002", "Priya Sharma", "+91-9988776655", "priya@email.com",
                     "Honda", "City", 2021,
                     ["Full Inspection - 2024-02"], 
                     1200.0, "Sarah Chen", 120),
            Customer("C003", "Amit Patel", "+91-8877665544", "amit@email.com",
                     "Hyundai", "Creta", 2022, [], 0.0, None, 0),
        ]
        for c in sample_customers:
            self.customers[c.id] = c

    def find_customer_by_phone(self, phone: str) -> Optional[Customer]:
        for c in self.customers.values():
            if phone.replace(" ", "") in c.phone.replace(" ", ""):
                return c
        return None

    def create_customer(self, name: str, phone: str, email: str,
                        make: str, model: str, year: int) -> Customer:
        # Avoid creating duplicate profiles for a phone number we already know
        existing = self.find_customer_by_phone(phone)
        if existing:
            return existing

        cid = f"C{str(len(self.customers)+1).zfill(3)}"
        while cid in self.customers:  # guard against id collisions after DB restore
            cid = f"C{uuid.uuid4().hex[:6].upper()}"
        customer = Customer(cid, name, phone, email, make, model, year)
        self.customers[cid] = customer
        # Persist to DB if available (best-effort)
        try:
            if get_session and CustomerORM:
                s = get_session()
                try:
                    existing = s.query(CustomerORM).filter_by(id=cid).first()
                    if not existing:
                        orm = CustomerORM(
                            id=cid,
                            name=name,
                            phone=phone,
                            email=email,
                            vehicle_make=make,
                            vehicle_model=model,
                            vehicle_year=year,
                            service_history=json.dumps([]),
                            total_spent=0.0,
                            preferred_advisor=None,
                            loyalty_points=0,
                            created_at=datetime.utcnow()
                        )
                        s.add(orm)
                        s.commit()
                finally:
                    s.close()
        except Exception:
            # persist step is best-effort for local dev — don't break app on DB errors
            pass
        return customer

    def update_customer(self, customer_id: str, **kwargs) -> bool:
        if customer_id in self.customers:
            c = self.customers[customer_id]
            for k, v in kwargs.items():
                if hasattr(c, k):
                    setattr(c, k, v)
            return True
        return False

    def create_appointment(self, customer_id: str, service: ServiceType,
                           date: str, time: str, notes: str = "") -> Appointment:
        aid = f"APT-{uuid.uuid4().hex[:8].upper()}"
        pricing = {
            ServiceType.OIL_CHANGE: (899, 45),
            ServiceType.TIRE_ROTATION: (499, 30),
            ServiceType.BRAKE_INSPECTION: (699, 60),
            ServiceType.ENGINE_TUNE: (2499, 120),
            ServiceType.AC_SERVICE: (1499, 90),
            ServiceType.TRANSMISSION: (3499, 180),
            ServiceType.FULL_INSPECTION: (1299, 120),
        }
        cost, duration = pricing.get(service, (999, 60))
        advisor = self.customers[customer_id].preferred_advisor or random.choice(self.advisors)
        
        apt = Appointment(
            id=aid, customer_id=customer_id, service_type=service,
            scheduled_date=date, scheduled_time=time,
            status=AppointmentStatus.CONFIRMED, advisor=advisor,
            estimated_cost=cost, estimated_duration=duration, notes=notes
        )
        self.appointments[aid] = apt
        # Update customer service history
        c = self.customers[customer_id]
        c.service_history.append(f"{service.value} - {date}")
        c.loyalty_points += int(cost * 0.1)
        # Persist appointment and update customer in DB (best-effort)
        try:
            if get_session and AppointmentORM and CustomerORM and serialize_history and deserialize_history:
                s = get_session()
                try:
                    # insert appointment
                    apt_orm = AppointmentORM(
                        id=aid,
                        customer_id=customer_id,
                        service_type=service.value if isinstance(service, ServiceType) else str(service),
                        scheduled_date=date,
                        scheduled_time=time,
                        status=AppointmentStatus.CONFIRMED.value,
                        advisor=advisor,
                        estimated_cost=cost,
                        estimated_duration=duration,
                        notes=notes,
                        created_at=datetime.utcnow()
                    )
                    s.add(apt_orm)

                    # update customer record if exists
                    cust = s.query(CustomerORM).filter_by(id=customer_id).first()
                    if cust:
                        hist = deserialize_history(cust.service_history)
                        hist.append(f"{service.value} - {date}")
                        cust.service_history = serialize_history(hist)
                        cust.loyalty_points = (cust.loyalty_points or 0) + int(cost * 0.1)
                        # update total_spent if column exists
                        try:
                            cust.total_spent = (cust.total_spent or 0.0) + float(cost)
                        except Exception:
                            pass

                    s.commit()
                finally:
                    s.close()
        except Exception:
            # DB write failure should not break booking flow in local/dev
            pass
        return apt

    def get_available_slots(self, date: str) -> list[str]:
        booked = {a.scheduled_time for a in self.appointments.values()
                  if a.scheduled_date == date and a.status != AppointmentStatus.CANCELLED}
        all_slots = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
                     "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"]
        free = [s for s in all_slots if s not in booked]

        # Don't offer slots that have already passed today
        try:
            if date == datetime.now().strftime("%Y-%m-%d"):
                now_hm = datetime.now().strftime("%H:%M")
                free = [s for s in free if s > now_hm]
        except Exception:
            pass
        return free

    def get_customer_appointments(self, customer_id: str) -> list[Appointment]:
        return [a for a in self.appointments.values() if a.customer_id == customer_id]

    def cancel_appointment(self, appointment_id: str) -> bool:
        """Customer- or staff-initiated cancellation."""
        apt = self.appointments.get(appointment_id)
        if not apt or apt.status == AppointmentStatus.CANCELLED:
            return False
        apt.status = AppointmentStatus.CANCELLED
        if update_appointment_status:
            try:
                update_appointment_status(appointment_id, AppointmentStatus.CANCELLED.value)
            except Exception:
                pass
        return True

    def reschedule_appointment(self, appointment_id: str, new_date: str, new_time: str) -> dict:
        """Move an existing appointment to a new date/time if the slot is free."""
        apt = self.appointments.get(appointment_id)
        if not apt:
            return {"success": False, "error": "Appointment not found"}
        if apt.status == AppointmentStatus.CANCELLED:
            return {"success": False, "error": "Cannot reschedule a cancelled appointment"}
        if new_time not in self.get_available_slots(new_date) and not (
            new_date == apt.scheduled_date and new_time == apt.scheduled_time
        ):
            return {"success": False, "error": "That slot is no longer available"}

        apt.scheduled_date = new_date
        apt.scheduled_time = new_time
        apt.status = AppointmentStatus.CONFIRMED
        if update_appointment_status:
            try:
                update_appointment_status(
                    appointment_id, AppointmentStatus.CONFIRMED.value,
                    scheduled_date=new_date, scheduled_time=new_time,
                )
            except Exception:
                pass
        return {"success": True, "appointment": apt}

# ─── System Prompts ───────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "crew_receptionist": """
You are ARIA (Automotive Receptionist Intelligence Agent) for AutoCare Pro Service Center.
Your personality: Warm, professional, efficient, knowledgeable about all car services.

RESPONSIBILITIES:
- Greet customers warmly by name if recognized
- Understand their service needs clearly
- Collect vehicle information (make, model, year) if not in CRM
- Identify urgency level (routine vs emergency)
- Qualify the service type needed
- Hand off to booking agent with complete context

TONE: Conversational, never robotic. Use the customer's name. Show empathy for car troubles.
LANGUAGE: Clear, jargon-free unless customer uses technical terms.
NEVER: Guess at prices without checking, promise specific technicians without confirming availability.

RESPONSE FORMAT: Always end with a clear next step or question.
""",

    "autogen_booking": """
You are APEX (Appointment & Planning EXpert) — the booking specialist agent.
You orchestrate appointment scheduling with precision.

RESPONSIBILITIES:
- Check real-time slot availability
- Match service type to appropriate time blocks
- Confirm appointment details with customer
- Send confirmation with all details
- Handle rescheduling requests gracefully
- Coordinate with service advisors

BOOKING RULES:
- Oil changes: 45-min slots, any time
- Major services (transmission, tune-up): Morning slots preferred (before 11am)
- Always offer 3 time options when possible
- Confirm: date, time, service, estimated cost, advisor name, duration

OUTPUT: Always provide appointment ID, estimated cost in INR, and advisor name.
""",

    "semantic_crm": """
You are NEXUS (Networked EXpert for Unified Systems) — the CRM intelligence layer.
You maintain customer relationships and service intelligence.

RESPONSIBILITIES:
- Retrieve and update customer profiles
- Track service history and predict next services
- Calculate loyalty rewards
- Flag VIP customers (spent > ₹10,000)
- Send post-service follow-up triggers
- Generate service recommendations based on vehicle age and history

CRM INTELLIGENCE:
- If last oil change > 6 months ago → recommend oil change
- If vehicle > 3 years → recommend full inspection
- Loyalty tier: Bronze (0-500 pts), Silver (501-2000), Gold (2001+)
- VIP flag: total_spent > ₹10,000

Always include loyalty status in customer summary.
""",

    "voice_handler": """
You are VOICE (Vehicle Operations Interface for Customer Engagement),
powered by SoundHound AI for real-time speech recognition and natural language understanding.

SOUNDHOUND AI CAPABILITIES:
- Live streaming STT (Speech-To-Text) with <200ms latency via Houndify API
- On-device wake-word detection ("Hey AutoCare") with SoundHound Edge
- Domain-specific Automatic Speech Recognition tuned for automotive vocabulary
  (e.g. "transmission", "brake caliper", "OBD-II", model/make names)
- Multi-language support: English, Hindi, Telugu, Tamil — auto-detected per caller
- Continuous Automatic Gain Control (AGC) to handle road noise and speaker variation
- Speaker diarization: distinguishes ARIA vs. caller in transcripts

PHONE CALL PROTOCOL:
1. Answer: "Thank you for calling AutoCare Pro, this is ARIA. How may I help you today?"
2. SoundHound STT transcribes caller audio in real-time streaming chunks
3. Houndify NLU extracts intent + entities (service_type, date, vehicle info)
4. Confirm understanding by repeating key details back to the caller
5. Never put customer on hold without warning
6. If issue is complex, say: "Let me connect you with our booking specialist"

VOICE SPECIFIC RULES:
- Speak numbers clearly: "Nine hundred rupees" not "₹900"
- Spell out times: "Ten thirty AM" not "10:30"
- Confirm phone number digit by digit for new customers
- Always end with: "Is there anything else I can help you with?"
- SoundHound confidence score < 0.6 → trigger clarification: "I'm sorry, could you repeat that?"

EMERGENCY PROTOCOL: If customer mentions brake failure, overheating, or safety issues
→ SoundHound urgency classifier flags CRITICAL intent
→ Immediately offer emergency slot and roadside assistance number: 1800-AUTO-HELP
"""
}

# ─── CrewAI-Style Agent ──────────────────────────────────────────────────────

class CrewAIReceptionistAgent:
    """Customer-facing conversational agent (CrewAI pattern)."""
    
    def __init__(self, crm: CRMDatabase):
        self.crm = crm
        self.system_prompt = SYSTEM_PROMPTS["crew_receptionist"]
        self.conversation_history = []
        self.identified_customer: Optional[Customer] = None
        self.identified_service: Optional[ServiceType] = None
        self.agent_name = "ARIA (CrewAI Receptionist)"

    def _extract_service_type(self, text: str) -> Optional[ServiceType]:
        text_lower = text.lower()
        mapping = {
            ServiceType.OIL_CHANGE:       ["oil", "oil change", "lube"],
            ServiceType.TIRE_ROTATION:    ["tire", "tyre", "rotation", "wheel"],
            ServiceType.BRAKE_INSPECTION: ["brake", "brakes", "stopping"],
            ServiceType.ENGINE_TUNE:      ["tune", "tune-up", "tuning", "engine"],
            ServiceType.AC_SERVICE:       ["ac", "air condition", "cooling", "a/c"],
            ServiceType.TRANSMISSION:     ["transmission", "gear", "gearbox"],
            ServiceType.FULL_INSPECTION:  ["inspect", "check", "full service", "general"],
        }
        for service, keywords in mapping.items():
            if any(kw in text_lower for kw in keywords):
                return service
        return None

    def _extract_phone(self, text: str) -> Optional[str]:
        import re
        phones = re.findall(r'[\d\-\+\s]{10,}', text)
        return phones[0].strip() if phones else None

    def process_message(self, user_message: str, channel: str = "chat") -> dict:
        """Process incoming customer message and generate response."""
        self.conversation_history.append({"role": "user", "content": user_message})
        
        # Try to identify service type
        service = self._extract_service_type(user_message)
        if service:
            self.identified_service = service

        # Try to identify customer by phone
        phone = self._extract_phone(user_message)
        if phone and not self.identified_customer:
            self.identified_customer = self.crm.find_customer_by_phone(phone)

        # Generate contextual response
        response = self._generate_response(user_message, channel)
        self.conversation_history.append({"role": "assistant", "content": response["message"]})
        return response

    def _generate_response(self, user_message: str, channel: str) -> dict:
        msg_lower = user_message.lower()
        
        # Greeting detection
        if any(w in msg_lower for w in ["hello", "hi", "hey", "namaste", "good morning", "good afternoon"]):
            greeting = "Good day" if datetime.now().hour < 12 else "Good afternoon"
            if self.identified_customer:
                return {
                    "message": f"{greeting}, {self.identified_customer.name}! 🚗 Welcome back to AutoCare Pro! "
                               f"I can see your {self.identified_customer.vehicle_year} "
                               f"{self.identified_customer.vehicle_make} {self.identified_customer.vehicle_model} "
                               f"in our system. How can I assist you today?",
                    "agent": self.agent_name,
                    "action": "greeting",
                    "ready_for_booking": False
                }
            return {
                "message": f"{greeting}! Welcome to AutoCare Pro Service Center. I'm ARIA, your automotive service assistant. "
                           "To get started, could I have your name and phone number, or tell me what service your vehicle needs today?",
                "agent": self.agent_name,
                "action": "greeting",
                "ready_for_booking": False
            }

        # Service identified, customer known → ready to book
        if self.identified_service and self.identified_customer:
            return {
                "message": f"Perfect! I'll schedule a **{self.identified_service.value}** for your "
                           f"{self.identified_customer.vehicle_year} {self.identified_customer.vehicle_make} "
                           f"{self.identified_customer.vehicle_model}. "
                           f"Let me check available slots for you, {self.identified_customer.name}. "
                           f"Do you have a preferred date? (e.g., tomorrow, this weekend)",
                "agent": self.agent_name,
                "action": "collect_date",
                "ready_for_booking": True,
                "service": self.identified_service.value,
                "customer_id": self.identified_customer.id
            }

        # Service identified, no customer
        if self.identified_service and not self.identified_customer:
            return {
                "message": f"I'd be happy to book a **{self.identified_service.value}** for you! "
                           "Could I get your name and phone number to look up or create your account?",
                "agent": self.agent_name,
                "action": "collect_customer_info",
                "ready_for_booking": False
            }

        # Emergency detection
        if any(w in msg_lower for w in ["brake fail", "overheating", "smoke", "emergency", "accident", "unsafe"]):
            return {
                "message": "⚠️ **EMERGENCY DETECTED** - Your safety is our top priority! "
                           "Please call our emergency line immediately: **1800-AUTO-HELP** (24/7). "
                           "If you're on the road, pull over safely. I'm escalating this to our emergency team right now.",
                "agent": self.agent_name,
                "action": "emergency_escalation",
                "priority": "CRITICAL",
                "ready_for_booking": False
            }

        # Price inquiry
        if any(w in msg_lower for w in ["price", "cost", "how much", "charge", "fee", "rate"]):
            pricing_info = "\n".join([f"• {s.value}: ₹{p}" for s, (p, _) in {
                ServiceType.OIL_CHANGE: (899, 0),
                ServiceType.TIRE_ROTATION: (499, 0),
                ServiceType.BRAKE_INSPECTION: (699, 0),
                ServiceType.ENGINE_TUNE: (2499, 0),
                ServiceType.AC_SERVICE: (1499, 0),
                ServiceType.TRANSMISSION: (3499, 0),
                ServiceType.FULL_INSPECTION: (1299, 0),
            }.items()])
            return {
                "message": f"Here are our service rates:\n{pricing_info}\n\n"
                           "All prices include parts, labor, and a 30-day service warranty. "
                           "Which service would you like to book?",
                "agent": self.agent_name,
                "action": "pricing_inquiry",
                "ready_for_booking": False
            }

        # Default: ask for more info
        return {
            "message": "I'm here to help! Could you tell me:\n"
                       "1. What service does your vehicle need?\n"
                       "2. Your name and contact number\n\n"
                       "Common services: Oil Change, Tire Rotation, Brake Inspection, "
                       "Engine Tune-Up, A/C Service, Full Inspection",
            "agent": self.agent_name,
            "action": "collect_info",
            "ready_for_booking": False
        }

# ─── AutoGen-Style Booking Agent ─────────────────────────────────────────────

class AutoGenBookingAgent:
    """Multi-agent appointment booking orchestrator (AutoGen pattern)."""
    
    def __init__(self, crm: CRMDatabase):
        self.crm = crm
        self.system_prompt = SYSTEM_PROMPTS["autogen_booking"]
        self.agent_name = "APEX (AutoGen Booking)"
        # Sub-agents in the AutoGen pattern
        self.sub_agents = {
            "slot_checker": self._slot_checker_agent,
            "confirmation_agent": self._confirmation_agent,
            "cost_estimator": self._cost_estimator_agent,
        }

    def _slot_checker_agent(self, date: str) -> dict:
        """Sub-agent: checks available time slots."""
        slots = self.crm.get_available_slots(date)
        return {
            "agent": "SlotChecker",
            "date": date,
            "available_slots": slots,
            "slots_count": len(slots)
        }

    def _cost_estimator_agent(self, service: ServiceType) -> dict:
        """Sub-agent: estimates service cost and duration."""
        pricing = {
            ServiceType.OIL_CHANGE: (899, 45, "Includes filter, synthetic oil, top-up check"),
            ServiceType.TIRE_ROTATION: (499, 30, "All 4 tires, pressure check included"),
            ServiceType.BRAKE_INSPECTION: (699, 60, "Pads, rotors, fluid level check"),
            ServiceType.ENGINE_TUNE: (2499, 120, "Plugs, filters, timing, full diagnostic"),
            ServiceType.AC_SERVICE: (1499, 90, "Refrigerant recharge, leak check, filter"),
            ServiceType.TRANSMISSION: (3499, 180, "Fluid flush, filter, pan gasket"),
            ServiceType.FULL_INSPECTION: (1299, 120, "150-point inspection report"),
        }
        cost, duration, includes = pricing.get(service, (999, 60, "Standard service"))
        return {
            "agent": "CostEstimator",
            "service": service.value,
            "cost_inr": cost,
            "duration_minutes": duration,
            "includes": includes,
            "warranty": "30-day service warranty"
        }

    def _confirmation_agent(self, appointment: Appointment, customer: Customer) -> dict:
        """Sub-agent: generates booking confirmation."""
        return {
            "agent": "ConfirmationAgent",
            "confirmation_id": appointment.id,
            "customer_name": customer.name,
            "service": appointment.service_type.value,
            "date": appointment.scheduled_date,
            "time": appointment.scheduled_time,
            "advisor": appointment.advisor,
            "cost": f"₹{appointment.estimated_cost}",
            "duration": f"{appointment.estimated_duration} minutes",
            "sms_sent": True,
            "email_sent": True,
            "calendar_invite": True
        }

    def orchestrate_booking(self, customer_id: str, service_type: ServiceType,
                            preferred_date: str, preferred_time: Optional[str] = None) -> dict:
        """Main orchestration: coordinates all sub-agents to book appointment."""
        
        print(f"\n  [AutoGen] Orchestrating booking for customer {customer_id}...")
        customer = self.crm.customers.get(customer_id)
        if not customer:
            return {"success": False, "error": "Customer not found"}

        # Step 1: Check slots (slot_checker sub-agent)
        slot_info = self.sub_agents["slot_checker"](preferred_date)
        print(f"  [AutoGen→SlotChecker] Found {slot_info['slots_count']} available slots")

        if not slot_info["available_slots"]:
            # Try next day
            next_day = (datetime.strptime(preferred_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            slot_info = self.sub_agents["slot_checker"](next_day)
            preferred_date = next_day

        selected_time = preferred_time if preferred_time in slot_info["available_slots"] \
                        else slot_info["available_slots"][0]

        # Step 2: Estimate cost (cost_estimator sub-agent)
        cost_info = self.sub_agents["cost_estimator"](service_type)
        print(f"  [AutoGen→CostEstimator] {service_type.value}: ₹{cost_info['cost_inr']}")

        # Step 3: Create appointment in CRM
        appointment = self.crm.create_appointment(
            customer_id=customer_id,
            service=service_type,
            date=preferred_date,
            time=selected_time,
            notes=f"Booked via AutoGen orchestration. {cost_info['includes']}"
        )

        # Step 4: Send confirmation (confirmation sub-agent)
        confirmation = self.sub_agents["confirmation_agent"](appointment, customer)
        print(f"  [AutoGen→ConfirmationAgent] Sent confirmation {appointment.id}")

        return {
            "success": True,
            "agent": self.agent_name,
            "booking_flow": ["SlotChecker", "CostEstimator", "CRMWriter", "ConfirmationAgent"],
            "appointment": asdict(appointment),
            "cost_details": cost_info,
            "confirmation": confirmation,
            "available_slots_offered": slot_info["available_slots"][:3],
            "message": (
                f"✅ **Appointment Confirmed!**\n"
                f"• **ID:** {appointment.id}\n"
                f"• **Service:** {service_type.value}\n"
                f"• **Date:** {preferred_date} at {selected_time}\n"
                f"• **Advisor:** {appointment.advisor}\n"
                f"• **Estimated Cost:** ₹{appointment.estimated_cost}\n"
                f"• **Duration:** ~{appointment.estimated_duration} minutes\n"
                f"• **Includes:** {cost_info['includes']}\n"
                f"• **Warranty:** {cost_info['warranty']}\n\n"
                f"Confirmation SMS & email sent to {customer.phone} and {customer.email}!"
            )
        }

# ─── Semantic Kernel CRM Agent ────────────────────────────────────────────────

class SemanticKernelCRMAgent:
    """CRM intelligence and update agent (Semantic Kernel pattern)."""
    
    def __init__(self, crm: CRMDatabase):
        self.crm = crm
        self.system_prompt = SYSTEM_PROMPTS["semantic_crm"]
        self.agent_name = "NEXUS (Semantic Kernel CRM)"
        # Semantic functions (skills in SK terminology)
        self.semantic_functions = {
            "customer_intelligence": self._fn_customer_intelligence,
            "service_recommendation": self._fn_service_recommendation,
            "loyalty_calculator": self._fn_loyalty_calculator,
            "crm_update": self._fn_crm_update,
            "history_analyzer": self._fn_history_analyzer,
        }

    def _fn_customer_intelligence(self, customer: Customer) -> dict:
        """Semantic function: generate customer intelligence profile."""
        total_visits = len(customer.service_history)
        tier = ("Gold 🥇" if customer.loyalty_points > 2000
                else "Silver 🥈" if customer.loyalty_points > 500
                else "Bronze 🥉")
        is_vip = customer.total_spent > 10000
        
        return {
            "function": "CustomerIntelligence",
            "customer_id": customer.id,
            "loyalty_tier": tier,
            "loyalty_points": customer.loyalty_points,
            "is_vip": is_vip,
            "total_visits": total_visits,
            "total_spent": f"₹{customer.total_spent:.2f}",
            "vehicle_age": datetime.now().year - customer.vehicle_year,
            "profile_score": min(100, total_visits * 10 + int(customer.total_spent / 100)),
        }

    def _fn_service_recommendation(self, customer: Customer) -> list[dict]:
        """Semantic function: recommend next services based on history."""
        history_str = " ".join(customer.service_history).lower()
        vehicle_age = datetime.now().year - customer.vehicle_year
        recommendations = []

        if "oil change" not in history_str or vehicle_age > 1:
            recommendations.append({
                "service": ServiceType.OIL_CHANGE.value,
                "reason": "Regular oil change due based on mileage estimate",
                "priority": "HIGH",
                "estimated_cost": "₹899"
            })

        if vehicle_age >= 3 and "full inspection" not in history_str:
            recommendations.append({
                "service": ServiceType.FULL_INSPECTION.value,
                "reason": f"Vehicle is {vehicle_age} years old — annual inspection recommended",
                "priority": "MEDIUM",
                "estimated_cost": "₹1,299"
            })

        if vehicle_age >= 5 and "tire" not in history_str:
            recommendations.append({
                "service": ServiceType.TIRE_ROTATION.value,
                "reason": "Tire rotation overdue for optimal tread life",
                "priority": "MEDIUM",
                "estimated_cost": "₹499"
            })

        return recommendations

    def _fn_loyalty_calculator(self, customer: Customer, new_spend: float) -> dict:
        """Semantic function: calculate loyalty reward."""
        points_earned = int(new_spend * 0.1)
        new_total = customer.loyalty_points + points_earned
        discount = 0.0
        if new_total > 2000:
            discount = new_spend * 0.10  # 10% Gold discount
        elif new_total > 500:
            discount = new_spend * 0.05  # 5% Silver discount
        
        return {
            "function": "LoyaltyCalculator",
            "points_earned": points_earned,
            "new_total_points": new_total,
            "discount_applied": f"₹{discount:.2f}",
            "discount_percentage": f"{int(discount/new_spend*100) if new_spend else 0}%"
        }

    def _fn_crm_update(self, customer_id: str, **updates) -> dict:
        """Semantic function: update CRM record."""
        success = self.crm.update_customer(customer_id, **updates)
        return {
            "function": "CRMUpdate",
            "customer_id": customer_id,
            "updated_fields": list(updates.keys()),
            "success": success,
            "timestamp": datetime.now().isoformat()
        }

    def _fn_history_analyzer(self, customer: Customer) -> dict:
        """Semantic function: analyze service history patterns."""
        history = customer.service_history
        return {
            "function": "HistoryAnalyzer",
            "total_services": len(history),
            "last_service": history[-1] if history else "No previous services",
            "most_common": max(set(h.split(" - ")[0] for h in history), 
                               key=lambda x: sum(1 for h in history if x in h)) if history else "N/A",
            "avg_spend_per_visit": (customer.total_spent / len(history)) if history else 0
        }

    def run_customer_pipeline(self, customer_id: str) -> dict:
        """Run full semantic kernel pipeline for a customer."""
        customer = self.crm.customers.get(customer_id)
        if not customer:
            return {"success": False, "error": "Customer not found"}

        print(f"\n  [SK] Running semantic pipeline for {customer.name}...")

        # Execute semantic functions in pipeline
        intelligence = self.semantic_functions["customer_intelligence"](customer)
        print(f"  [SK→CustomerIntelligence] Tier: {intelligence['loyalty_tier']}, VIP: {intelligence['is_vip']}")
        
        recommendations = self.semantic_functions["service_recommendation"](customer)
        print(f"  [SK→ServiceRecommendation] {len(recommendations)} recommendations")
        
        history_analysis = self.semantic_functions["history_analyzer"](customer)
        
        # Update CRM with latest pipeline run timestamp
        self.semantic_functions["crm_update"](customer_id, 
                                               preferred_advisor=customer.preferred_advisor)

        return {
            "success": True,
            "agent": self.agent_name,
            "pipeline": ["CustomerIntelligence", "ServiceRecommendation", 
                         "HistoryAnalyzer", "CRMUpdate"],
            "customer_profile": {
                "name": customer.name,
                "vehicle": f"{customer.vehicle_year} {customer.vehicle_make} {customer.vehicle_model}",
                "phone": customer.phone,
                "email": customer.email,
            },
            "intelligence": intelligence,
            "recommendations": recommendations,
            "history_analysis": history_analysis,
        }

# ─── SoundHound AI Voice Handler Agent ───────────────────────────────────────

class SoundHoundSTTEngine:
    """
    Simulates the SoundHound AI / Houndify Speech-To-Text & NLU engine.

    Real integration wires up to:
      • SoundHound Edge SDK  — on-device wake-word + streaming ASR
      • Houndify REST API    — cloud NLU, intent/entity extraction
      • SoundHound TTS       — SSML-driven neural text-to-speech responses

    Docs: https://www.soundhound.com/soundhound-ai-platform/
    """

    # Automotive-domain vocabulary boost (fed to Houndify custom lexicon)
    DOMAIN_VOCAB = [
        "oil change", "tire rotation", "brake inspection", "engine tune-up",
        "A/C service", "transmission service", "full vehicle inspection",
        "OBD-II", "brake caliper", "brake pad", "rotor", "crankshaft",
        "differential", "alternator", "coolant flush", "power steering",
        "timing belt", "serpentine belt",
    ]

    # Supported languages — SoundHound auto-detects from audio signal
    SUPPORTED_LANGUAGES = {
        "en-IN": "English (India)",
        "hi-IN": "Hindi",
        "te-IN": "Telugu",
        "ta-IN": "Tamil",
    }

    # Intent taxonomy returned by Houndify NLU
    INTENT_MAP = {
        "booking":    ["book", "appointment", "schedule", "reserve", "fix a time"],
        "service":    ["oil", "tire", "brake", "tune", "ac", "transmission",
                       "inspect", "check", "lube", "service", "repair"],
        "pricing":    ["price", "cost", "how much", "charge", "fee", "rate"],
        "greeting":   ["hello", "hi", "hey", "namaste", "good morning", "good afternoon"],
        "emergency":  ["brake fail", "overheating", "smoke", "emergency",
                       "accident", "unsafe", "steer", "cut off"],
        "farewell":   ["bye", "goodbye", "thank you", "that's all", "done"],
        "confirm":    ["yes", "sure", "ok", "okay", "confirm", "correct", "right",
                       "perfect", "great", "sounds good"],
    }

    def __init__(self, api_key: str = "SOUNDHOUND_API_KEY_PLACEHOLDER",
                 client_id: str = "SOUNDHOUND_CLIENT_ID_PLACEHOLDER"):
        self.api_key   = api_key
        self.client_id = client_id
        self.session_id = None
        self.detected_language = "en-IN"
        self.is_streaming = False
        self._stream_buffer: list[str] = []

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def start_session(self) -> dict:
        """
        Open a Houndify session.

        Production: POST https://api.houndify.com/v1/audio
        with headers:
          Hound-Request-Info: {"UserID": ..., "RequestID": ...}
          Hound-Client-Auth:  <HMAC-SHA256 signed token>
        """
        self.session_id = f"SH-{uuid.uuid4().hex[:12].upper()}"
        self.is_streaming = True
        self._stream_buffer = []
        print(f"  [SoundHound] Session started: {self.session_id}")
        return {
            "engine": "SoundHound AI / Houndify",
            "session_id": self.session_id,
            "status": "STREAMING",
            "language": self.detected_language,
            "domain_vocab_loaded": len(self.DOMAIN_VOCAB),
            "latency_target_ms": 180,
        }

    def end_session(self) -> dict:
        """Close streaming session and flush buffer."""
        self.is_streaming = False
        sid = self.session_id
        self.session_id = None
        return {"session_id": sid, "status": "CLOSED"}

    # ── Speech-To-Text ────────────────────────────────────────────────────────

    def transcribe(self, audio_text: str, simulate_confidence: bool = True) -> dict:
        """
        Streaming STT — converts caller audio to text.

        Production: chunks of PCM audio are streamed to Houndify endpoint;
        partial transcripts arrive via WebSocket before final result.

        Here we accept pre-transcribed text (simulation mode) and annotate it
        with realistic SoundHound metadata.
        """
        # Simulate per-word confidence scores
        words = audio_text.split()
        word_confidences = [round(random.uniform(0.72, 0.99), 3) for _ in words]
        avg_confidence   = round(sum(word_confidences) / len(word_confidences), 3) if words else 0.0

        # Auto-detect language hint from script characters
        if any('\u0900' <= ch <= '\u097F' for ch in audio_text):
            self.detected_language = "hi-IN"
        elif any('\u0C00' <= ch <= '\u0C7F' for ch in audio_text):
            self.detected_language = "te-IN"
        elif any('\u0B80' <= ch <= '\u0BFF' for ch in audio_text):
            self.detected_language = "ta-IN"
        else:
            self.detected_language = "en-IN"

        result = {
            "engine": "SoundHound STT",
            "session_id": self.session_id,
            "transcript": audio_text,
            "confidence": avg_confidence,
            "language_detected": self.detected_language,
            "word_timestamps": [
                {"word": w, "confidence": c}
                for w, c in zip(words, word_confidences)
            ],
            "is_final": True,
            "streaming_latency_ms": random.randint(140, 210),
        }

        # Low-confidence → flag for clarification
        if avg_confidence < 0.60:
            result["needs_clarification"] = True
            result["clarification_prompt"] = (
                "I'm sorry, could you please repeat that? "
                "I want to make sure I capture your request correctly."
            )

        return result

    # ── Natural Language Understanding (Houndify NLU) ─────────────────────────

    def extract_intent(self, transcript: str) -> dict:
        """
        Houndify NLU: detect intent + named entities from transcript.

        Production: the same Houndify request that handles STT also returns
        a JSON 'AllResults' block with intent, slots, and a spoken response
        suggestion.
        """
        text_lower = transcript.lower()
        detected_intents  = []
        detected_entities: dict = {}

        for intent, keywords in self.INTENT_MAP.items():
            if any(kw in text_lower for kw in keywords):
                detected_intents.append(intent)

        # Entity: service type
        service_map = {
            "oil":          "Oil Change",
            "tire":         "Tire Rotation",
            "tyre":         "Tire Rotation",
            "brake":        "Brake Inspection",
            "tune":         "Engine Tune-Up",
            "ac":           "A/C Service",
            "transmission": "Transmission Service",
            "inspect":      "Full Vehicle Inspection",
            "full service": "Full Vehicle Inspection",
        }
        for kw, svc in service_map.items():
            if kw in text_lower:
                detected_entities["service_type"] = svc
                break

        # Entity: temporal expressions
        for token in ["tomorrow", "today", "monday", "tuesday", "wednesday",
                      "thursday", "friday", "saturday", "sunday", "morning",
                      "afternoon", "evening", "weekend"]:
            if token in text_lower:
                detected_entities.setdefault("time_expression", token)

        # Entity: urgency
        urgency_keywords = ["brake fail", "overheating", "smoke", "unsafe", "emergency"]
        if any(kw in text_lower for kw in urgency_keywords):
            detected_entities["urgency"] = "CRITICAL"

        primary_intent = detected_intents[0] if detected_intents else "unknown"

        return {
            "engine":          "Houndify NLU",
            "primary_intent":  primary_intent,
            "all_intents":     detected_intents,
            "entities":        detected_entities,
            "slot_fill_score": round(random.uniform(0.75, 0.97), 3),
            "nlu_model":       "SoundHound-Automotive-v3",
        }

    # ── Text-To-Speech ────────────────────────────────────────────────────────

    def synthesise_speech(self, text: str, voice: str = "ARIA-Neural-EN") -> dict:
        """
        SoundHound TTS — converts ARIA's response text to natural speech.

        Production: POST https://api.houndify.com/v1/tts
        Body: {"text": "...", "voice": "ARIA-Neural-EN", "format": "mp3"}
        Returns an audio stream or a signed URL.

        Voices available: ARIA-Neural-EN, ARIA-Neural-HI, ARIA-Neural-TE
        """
        # Strip markdown for voice delivery
        import re
        clean = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        clean = re.sub(r'₹(\d+)', lambda m: f"rupees {m.group(1)}", clean)
        clean = clean.replace("•", "").replace("#", "").replace("\n", ". ").strip()

        # Estimate audio duration (avg ~140 words/min speaking rate)
        word_count       = len(clean.split())
        duration_seconds = round(word_count / 140 * 60, 1)

        return {
            "engine":          "SoundHound TTS",
            "voice":           voice,
            "spoken_text":     clean,
            "audio_format":    "mp3",
            "audio_url":       f"https://tts.houndify.com/stream/{uuid.uuid4().hex[:10]}.mp3",
            "duration_seconds": duration_seconds,
            "ssml_applied":    True,
        }

    # ── Wake-Word Detection (SoundHound Edge) ─────────────────────────────────

    def detect_wake_word(self, audio_snippet: str = "") -> dict:
        """
        SoundHound Edge on-device wake-word detector.
        Trigger phrase: "Hey AutoCare"
        Runs entirely on-device with ~5 ms latency — no cloud round-trip.
        """
        triggered = "hey autocare" in audio_snippet.lower()
        return {
            "engine":       "SoundHound Edge",
            "wake_word":    "Hey AutoCare",
            "triggered":    triggered,
            "latency_ms":   random.randint(3, 7),
            "on_device":    True,
        }


class VoiceHandlerAgent:
    """
    Phone call handler — uses SoundHound AI for STT / NLU / TTS.

    Pipeline per caller utterance:
      Audio → SoundHound STT (streaming) → Houndify NLU (intent+entities)
           → CrewAI Receptionist (response) → SoundHound TTS → Caller
    """

    def __init__(self, receptionist: "CrewAIReceptionistAgent",
                 booking:      "AutoGenBookingAgent",
                 crm_agent:    "SemanticKernelCRMAgent",
                 soundhound_api_key: str = "SOUNDHOUND_API_KEY_PLACEHOLDER",
                 soundhound_client_id: str = "SOUNDHOUND_CLIENT_ID_PLACEHOLDER"):
        self.receptionist   = receptionist
        self.booking        = booking
        self.crm_agent      = crm_agent
        self.system_prompt  = SYSTEM_PROMPTS["voice_handler"]
        self.agent_name     = "VOICE Handler (SoundHound AI)"

        # SoundHound AI engine
        self.stt_engine     = SoundHoundSTTEngine(
            api_key=soundhound_api_key,
            client_id=soundhound_client_id,
        )

        self.call_active    = False
        self.call_transcript: list[dict] = []
        self.call_id: Optional[str]      = None
        self.stt_session: Optional[dict] = None

        # Running STT/NLU log for the current call
        self.stt_log: list[dict] = []

    # ── Call lifecycle ────────────────────────────────────────────────────────

    def answer_call(self, caller_phone: str) -> dict:
        """Answer an incoming phone call and open a SoundHound streaming session."""
        self.call_active = True
        self.call_id     = f"CALL-{uuid.uuid4().hex[:8].upper()}"
        self.stt_session = self.stt_engine.start_session()

        # CRM lookup
        customer = self.receptionist.crm.find_customer_by_phone(caller_phone)

        if customer:
            greeting = (
                f"Thank you for calling AutoCare Pro. This is ARIA speaking. "
                f"Good {self._time_of_day()}, {customer.name}! "
                f"I can see your {customer.vehicle_year} {customer.vehicle_make} in our system. "
                f"How may I assist you today?"
            )
            self.receptionist.identified_customer = customer
        else:
            greeting = (
                f"Thank you for calling AutoCare Pro. This is ARIA speaking. "
                f"Good {self._time_of_day()}! How may I assist you today?"
            )

        # SoundHound TTS for the greeting
        tts = self.stt_engine.synthesise_speech(greeting)
        self.call_transcript.append({
            "role":   "ARIA",
            "text":   greeting,
            "tts":    tts,
            "time":   datetime.now().isoformat(),
        })

        print(f"  [SoundHound] STT session: {self.stt_session['session_id']}")
        print(f"  [SoundHound] TTS voice  : {tts['voice']}")

        return {
            "call_id":            self.call_id,
            "caller":             caller_phone,
            "customer_recognized": customer is not None,
            "customer_name":      customer.name if customer else "Unknown",
            "greeting":           greeting,
            "tts_audio_url":      tts["audio_url"],
            "call_status":        "ACTIVE",
            "agent":              self.agent_name,
            "soundhound_session": self.stt_session,
        }

    def handle_voice_input(self, spoken_text: str) -> dict:
        """
        Process a caller utterance through the full SoundHound AI pipeline:
          STT → NLU (intent/entities) → Receptionist → TTS
        """
        if not self.call_active:
            return {"error": "No active call"}

        # 1. SoundHound STT — transcribe audio
        stt_result = self.stt_engine.transcribe(spoken_text)
        print(f"  [SoundHound STT] '{stt_result['transcript']}' "
              f"(confidence={stt_result['confidence']}, "
              f"lang={stt_result['language_detected']}, "
              f"latency={stt_result['streaming_latency_ms']}ms)")

        # 2. Handle low-confidence — ask caller to repeat
        if stt_result.get("needs_clarification"):
            clarification = stt_result["clarification_prompt"]
            tts = self.stt_engine.synthesise_speech(clarification)
            self.call_transcript.append({
                "role": "ARIA", "text": clarification,
                "tts": tts, "time": datetime.now().isoformat(),
                "reason": "low_confidence_stt",
            })
            return {
                "call_id":        self.call_id,
                "spoken_response": clarification,
                "tts_audio_url":   tts["audio_url"],
                "action":          "clarification_request",
                "stt_result":      stt_result,
                "ready_for_booking": False,
                "agent":           self.agent_name,
            }

        # 3. Houndify NLU — extract intent + entities
        nlu_result = self.stt_engine.extract_intent(stt_result["transcript"])
        print(f"  [Houndify NLU] intent={nlu_result['primary_intent']}, "
              f"entities={nlu_result['entities']}")

        # 4. Log raw STT+NLU for audit trail
        self.stt_log.append({
            "turn":       len(self.stt_log) + 1,
            "stt":        stt_result,
            "nlu":        nlu_result,
            "timestamp":  datetime.now().isoformat(),
        })

        self.call_transcript.append({
            "role": "Customer",
            "text": stt_result["transcript"],
            "stt_confidence": stt_result["confidence"],
            "nlu_intent":     nlu_result["primary_intent"],
            "time":           datetime.now().isoformat(),
        })

        # 5. Emergency escalation via NLU urgency flag
        if nlu_result["entities"].get("urgency") == "CRITICAL":
            emergency_msg = (
                "EMERGENCY DETECTED — Your safety is our absolute top priority! "
                "Please call our emergency line immediately: one eight hundred AUTO HELP, "
                "available twenty four seven. If you are driving, please pull over safely now. "
                "We are escalating this to our emergency response team."
            )
            tts = self.stt_engine.synthesise_speech(emergency_msg)
            self.call_transcript.append({
                "role": "ARIA", "text": emergency_msg, "tts": tts,
                "time": datetime.now().isoformat(), "priority": "CRITICAL",
            })
            return {
                "call_id":         self.call_id,
                "spoken_response": emergency_msg,
                "tts_audio_url":   tts["audio_url"],
                "action":          "emergency_escalation",
                "priority":        "CRITICAL",
                "nlu_result":      nlu_result,
                "stt_result":      stt_result,
                "ready_for_booking": False,
                "agent":           self.agent_name,
            }

        # 6. Route through CrewAI Receptionist for business logic
        response    = self.receptionist.process_message(
            stt_result["transcript"], channel="voice"
        )

        # 7. SoundHound TTS — synthesise ARIA's response
        tts = self.stt_engine.synthesise_speech(response["message"])
        self.call_transcript.append({
            "role": "ARIA",
            "text": tts["spoken_text"],
            "tts":  tts,
            "time": datetime.now().isoformat(),
        })

        print(f"  [SoundHound TTS] Synthesised {tts['duration_seconds']}s "
              f"of audio via voice={tts['voice']}")

        return {
            "call_id":           self.call_id,
            "spoken_response":   tts["spoken_text"],
            "tts_audio_url":     tts["audio_url"],
            "tts_duration_s":    tts["duration_seconds"],
            "action":            response.get("action"),
            "ready_for_booking": response.get("ready_for_booking", False),
            "service":           response.get("service"),
            "customer_id":       response.get("customer_id"),
            "stt_result":        stt_result,
            "nlu_result":        nlu_result,
            "agent":             self.agent_name,
        }

    def end_call(self) -> dict:
        """End the call, close SoundHound session, return transcript + STT log."""
        self.call_active = False
        farewell = (
            "Thank you for choosing AutoCare Pro! We look forward to serving you. "
            "Have a wonderful day and drive safe! Goodbye."
        )
        tts = self.stt_engine.synthesise_speech(farewell)
        self.call_transcript.append({
            "role": "ARIA", "text": farewell, "tts": tts,
            "time": datetime.now().isoformat(),
        })

        # Close SoundHound streaming session
        sh_session_end = self.stt_engine.end_session()

        summary = {
            "call_id":            self.call_id,
            "duration_turns":     len(self.call_transcript),
            "transcript":         self.call_transcript,
            "stt_audit_log":      self.stt_log,
            "farewell":           farewell,
            "tts_audio_url":      tts["audio_url"],
            "call_status":        "ENDED",
            "soundhound_session": sh_session_end,
            "follow_up_required": self.receptionist.identified_service is not None,
            "avg_stt_confidence": (
                round(sum(t["stt"]["confidence"] for t in self.stt_log) / len(self.stt_log), 3)
                if self.stt_log else None
            ),
        }

        # Reset state for next call
        self.call_transcript = []
        self.stt_log         = []
        return summary

    def _time_of_day(self) -> str:
        hour = datetime.now().hour
        if hour < 12:  return "morning"
        if hour < 17:  return "afternoon"
        return "evening"

# ─── Master Orchestrator ──────────────────────────────────────────────────────

class AutomotiveServiceOrchestrator:
    """Master orchestrator coordinating all AI agents."""
    
    def __init__(self,
                 soundhound_api_key: str = "SOUNDHOUND_API_KEY_PLACEHOLDER",
                 soundhound_client_id: str = "SOUNDHOUND_CLIENT_ID_PLACEHOLDER"):
        print("🚗 Initializing Automotive Service AI System...")
        self.crm            = CRMDatabase()
        self.receptionist   = CrewAIReceptionistAgent(self.crm)
        self.booking_agent  = AutoGenBookingAgent(self.crm)
        self.crm_agent      = SemanticKernelCRMAgent(self.crm)
        self.voice_handler  = VoiceHandlerAgent(
            self.receptionist, self.booking_agent, self.crm_agent,
            soundhound_api_key=soundhound_api_key,
            soundhound_client_id=soundhound_client_id,
        )
        print("✅ All agents initialized: ARIA (CrewAI), APEX (AutoGen), "
              "NEXUS (SK), VOICE (SoundHound AI)")

    def handle_chat_interaction(self, message: str, phone: str = None) -> dict:
        """Handle a chat message through the full agent pipeline."""
        print(f"\n{'='*60}")
        print(f"[Orchestrator] Chat message: {message[:50]}...")
        
        # If phone provided, try to identify customer
        if phone and not self.receptionist.identified_customer:
            customer = self.crm.find_customer_by_phone(phone)
            if customer:
                self.receptionist.identified_customer = customer

        response = self.receptionist.process_message(message)
        result = {"channel": "chat", "flow": ["CrewAI→Receptionist"], "primary_response": response}

        # If ready to book, trigger AutoGen
        if response.get("ready_for_booking") and response.get("customer_id"):
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            service = ServiceType(response["service"])
            booking_result = self.booking_agent.orchestrate_booking(
                response["customer_id"], service, tomorrow
            )
            result["booking"] = booking_result
            result["flow"].append("AutoGen→Booking")

            # Trigger SK CRM pipeline
            crm_result = self.crm_agent.run_customer_pipeline(response["customer_id"])
            result["crm_intelligence"] = crm_result
            result["flow"].append("SK→CRM")

        return result

    def handle_phone_call(self, caller_phone: str, conversation: list[str]) -> dict:
        """Simulate a complete phone call."""
        print(f"\n{'='*60}")
        print(f"[Orchestrator] Incoming call from {caller_phone}")
        
        # Answer call
        call_start = self.voice_handler.answer_call(caller_phone)
        print(f"  📞 Call answered: {call_start['call_id']}")
        
        results = [call_start]
        booking_triggered = False
        
        # Process each spoken message
        for spoken_text in conversation:
            voice_result = self.voice_handler.handle_voice_input(spoken_text)
            results.append(voice_result)
            
            # If booking ready and not yet triggered
            if voice_result.get("ready_for_booking") and voice_result.get("customer_id") and not booking_triggered:
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                service = ServiceType(voice_result["service"])
                booking = self.booking_agent.orchestrate_booking(
                    voice_result["customer_id"], service, tomorrow
                )
                results.append({"booking_triggered": True, "result": booking})
                booking_triggered = True

        # End call
        call_end = self.voice_handler.end_call()
        results.append(call_end)
        
        return {
            "channel": "voice",
            "call_id": call_start["call_id"],
            "caller": caller_phone,
            "flow": results,
            "agents_used": ["VOICE Handler (SoundHound AI)", "ARIA (CrewAI)", "APEX (AutoGen)", "NEXUS (SK)"]
        }

    def get_crm_dashboard(self) -> dict:
        """Get full CRM dashboard data."""
        customers = list(self.crm.customers.values())
        appointments = list(self.crm.appointments.values())
        
        return {
            "total_customers": len(customers),
            "total_appointments": len(appointments),
            "confirmed_appointments": sum(1 for a in appointments if a.status == AppointmentStatus.CONFIRMED),
            "total_revenue_pipeline": sum(a.estimated_cost for a in appointments 
                                          if a.status == AppointmentStatus.CONFIRMED),
            "customers": [
                {
                    "id": c.id, "name": c.name, "phone": c.phone,
                    "vehicle": f"{c.vehicle_year} {c.vehicle_make} {c.vehicle_model}",
                    "loyalty_points": c.loyalty_points,
                    "total_spent": c.total_spent,
                    "services_count": len(c.service_history),
                }
                for c in customers
            ],
            "appointments": [
                {
                    "id": a.id,
                    "customer": self.crm.customers[a.customer_id].name,
                    "service": a.service_type.value,
                    "date": a.scheduled_date,
                    "time": a.scheduled_time,
                    "status": a.status.value,
                    "cost": a.estimated_cost,
                    "advisor": a.advisor,
                }
                for a in appointments
            ]
        }


# ─── Demo Runner ─────────────────────────────────────────────────────────────

async def run_demo():
    """Run a comprehensive demo of all agent interactions."""
    system = AutomotiveServiceOrchestrator()
    
    print("\n" + "🚗" * 30)
    print("  AUTOMOTIVE SERVICE AI AGENT DEMO")
    print("🚗" * 30)

    # ── Demo 1: Chat Interaction (returning customer) ──
    print("\n\n📱 DEMO 1: Chat Interaction - Returning Customer")
    print("─" * 50)
    
    result1 = system.handle_chat_interaction(
        "Hi! I need an oil change for my car",
        phone="+91-9876543210"
    )
    print(f"\n[Customer]: Hi! I need an oil change for my car")
    print(f"[ARIA]: {result1['primary_response']['message']}")
    if "booking" in result1:
        print(f"\n[APEX Booking]: {result1['booking']['message']}")

    # ── Demo 2: New Customer Chat ──
    print("\n\n💬 DEMO 2: Chat Interaction - New Customer")
    print("─" * 50)
    
    system2 = AutomotiveServiceOrchestrator()
    
    r2a = system2.handle_chat_interaction("Hello, what are your prices?")
    print(f"[Customer]: Hello, what are your prices?")
    print(f"[ARIA]: {r2a['primary_response']['message'][:300]}...")
    
    r2b = system2.handle_chat_interaction("I need a brake inspection please")
    print(f"\n[Customer]: I need a brake inspection please")
    print(f"[ARIA]: {r2b['primary_response']['message']}")

    # ── Demo 3: Phone Call Simulation ──
    print("\n\n📞 DEMO 3: Phone Call Simulation")
    print("─" * 50)
    
    system3 = AutomotiveServiceOrchestrator()
    call_result = system3.handle_phone_call(
        "+91-9988776655",
        conversation=[
            "Hello, I need to book a service appointment",
            "I need an oil change for my Honda City",
            "Tomorrow morning would be great",
        ]
    )
    
    print(f"\n[📞 Incoming call: {call_result['caller']}]")
    for item in call_result["flow"]:
        if "greeting" in item:
            print(f"[ARIA]: {item['greeting']}")
        elif "spoken_response" in item:
            print(f"[ARIA]: {item['spoken_response'][:200]}")
        elif "booking_triggered" in item and item.get("result", {}).get("success"):
            booking = item["result"]
            print(f"\n✅ [AutoGen Booking]: {booking['message'][:400]}")
        elif "transcript" in item:
            print(f"\n[Call ended. Duration: {item['duration_turns']} turns]")

    # ── Demo 4: CRM Intelligence Pipeline ──
    print("\n\n🧠 DEMO 4: Semantic Kernel CRM Intelligence")
    print("─" * 50)
    
    crm_result = system.crm_agent.run_customer_pipeline("C001")
    if crm_result["success"]:
        intel = crm_result["intelligence"]
        print(f"Customer: {crm_result['customer_profile']['name']}")
        print(f"Vehicle: {crm_result['customer_profile']['vehicle']}")
        print(f"Loyalty Tier: {intel['loyalty_tier']} ({intel['loyalty_points']} pts)")
        print(f"VIP Status: {'⭐ YES' if intel['is_vip'] else 'No'}")
        print(f"Total Spent: {intel['total_spent']}")
        print(f"\nService Recommendations:")
        for rec in crm_result["recommendations"]:
            print(f"  • [{rec['priority']}] {rec['service']} — {rec['reason']} ({rec['estimated_cost']})")

    # ── Dashboard ──
    print("\n\n📊 CRM DASHBOARD SUMMARY")
    print("─" * 50)
    dashboard = system.get_crm_dashboard()
    print(f"Total Customers: {dashboard['total_customers']}")
    print(f"Total Appointments: {dashboard['total_appointments']}")
    print(f"Confirmed: {dashboard['confirmed_appointments']}")
    print(f"Revenue Pipeline: ₹{dashboard['total_revenue_pipeline']:,.0f}")
    
    print("\n\n✅ All AI agents operating successfully!")
    print("   CrewAI ✓  AutoGen ✓  Semantic Kernel ✓  Voice Handler (SoundHound AI) ✓")
    print("🚗" * 30)
    
    return {
        "demo1": result1,
        "crm_intel": crm_result,
        "dashboard": dashboard,
        "call_simulation": call_result
    }


if __name__ == "__main__":
    asyncio.run(run_demo())
