"""
AutoCare Pro — Streamlit Frontend
===================================
Deploy: streamlit run streamlit_app.py
Cloud:  Push to GitHub → connect at share.streamlit.io
"""

import os
import re
import sys
from datetime import datetime, timedelta

import streamlit as st

# ── Allow import of main.py from same directory ──────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from main import AutomotiveServiceOrchestrator, ServiceType, AppointmentStatus

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AutoCare Pro",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .agent-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 2px;
    }
    .badge-crew   { background:#7c3aed; color:white; }
    .badge-autogen{ background:#0891b2; color:white; }
    .badge-sk     { background:#059669; color:white; }
    .badge-voice  { background:#d97706; color:white; }
    .chat-user {
        background: #e0f2fe;
        border-radius: 12px 12px 4px 12px;
        padding: 0.6rem 1rem;
        margin: 4px 0;
        text-align: right;
    }
    .chat-bot {
        background: #f0fdf4;
        border-radius: 12px 12px 12px 4px;
        padding: 0.6rem 1rem;
        margin: 4px 0;
    }
    .metric-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,.06);
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }
    .apt-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-left: 5px solid #0f3460;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .apt-cancelled { border-left-color: #dc2626; opacity: 0.7; }
    .apt-completed { border-left-color: #0891b2; }
</style>
""", unsafe_allow_html=True)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\-\s]{7,15}$")

# ─── Session State Initialisation ────────────────────────────────────────────
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = AutomotiveServiceOrchestrator()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []   # list of (role, text, agent)
if "chat_phone" not in st.session_state:
    st.session_state.chat_phone = ""
if "my_customer_id" not in st.session_state:
    st.session_state.my_customer_id = None
if "staff_authenticated" not in st.session_state:
    st.session_state.staff_authenticated = False

orchestrator: AutomotiveServiceOrchestrator = st.session_state.orchestrator

# ─── Helpers ──────────────────────────────────────────────────────────────────

def identify_customer_widget(key_prefix: str):
    """Shared 'find me / sign me up' widget so a customer can self-identify
    without ever seeing anyone else's profile. Returns the Customer object
    (or None) for the currently identified customer."""

    if st.session_state.my_customer_id:
        customer = orchestrator.crm.customers.get(st.session_state.my_customer_id)
        if customer:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.success(
                    f"👋 Welcome back, **{customer.name}** — "
                    f"{customer.vehicle_year} {customer.vehicle_make} {customer.vehicle_model} "
                    f"· ⭐ {customer.loyalty_points} pts"
                )
            with col2:
                if st.button("Switch account", key=f"{key_prefix}_switch"):
                    st.session_state.my_customer_id = None
                    st.rerun()
            return customer
        else:
            st.session_state.my_customer_id = None

    st.info("Enter your phone number to look up your profile, or register below if you're new.")
    lookup_phone = st.text_input(
        "Phone number", placeholder="+91-9876543210", key=f"{key_prefix}_lookup_phone"
    )
    if st.button("🔍 Find my profile", key=f"{key_prefix}_lookup_btn"):
        if not lookup_phone.strip():
            st.error("Please enter a phone number.")
        else:
            found = orchestrator.crm.find_customer_by_phone(lookup_phone.strip())
            if found:
                st.session_state.my_customer_id = found.id
                st.rerun()
            else:
                st.warning("No profile found for that number. Register below to create one.")

    with st.expander("🆕 New customer? Register here"):
        with st.form(f"{key_prefix}_register_form"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Full Name *")
                phone = st.text_input("Phone *", placeholder="+91-9876543210")
                email = st.text_input("Email *")
            with c2:
                make = st.text_input("Vehicle Make *", placeholder="Toyota")
                model = st.text_input("Vehicle Model *", placeholder="Innova")
                year = st.number_input(
                    "Vehicle Year *", min_value=1990,
                    max_value=datetime.now().year + 1, value=2021, step=1
                )
            reg_submit = st.form_submit_button("✅ Create my profile", type="primary")

        if reg_submit:
            errors = []
            if not all([name.strip(), phone.strip(), email.strip(), make.strip(), model.strip()]):
                errors.append("Please fill in all required fields.")
            if phone.strip() and not PHONE_RE.match(phone.strip()):
                errors.append("That doesn't look like a valid phone number.")
            if email.strip() and not EMAIL_RE.match(email.strip()):
                errors.append("Please enter a valid email address.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                customer = orchestrator.crm.create_customer(
                    name.strip(), phone.strip(), email.strip(), make.strip(), model.strip(), int(year)
                )
                st.session_state.my_customer_id = customer.id
                st.success(f"Profile created — welcome, {customer.name}!")
                st.rerun()

    return None


def build_receipt_text(apt, customer) -> str:
    service = apt.service_type.value if isinstance(apt.service_type, ServiceType) else str(apt.service_type)
    return (
        "AUTOCARE PRO — APPOINTMENT CONFIRMATION\n"
        "========================================\n"
        f"Appointment ID : {apt.id}\n"
        f"Customer       : {customer.name}\n"
        f"Phone          : {customer.phone}\n"
        f"Vehicle        : {customer.vehicle_year} {customer.vehicle_make} {customer.vehicle_model}\n"
        "----------------------------------------\n"
        f"Service        : {service}\n"
        f"Date & Time    : {apt.scheduled_date} at {apt.scheduled_time}\n"
        f"Advisor        : {apt.advisor}\n"
        f"Estimated Cost : Rs. {apt.estimated_cost:,.0f}\n"
        f"Duration       : ~{apt.estimated_duration} minutes\n"
        f"Status         : {apt.status.value if hasattr(apt.status, 'value') else apt.status}\n"
        "----------------------------------------\n"
        "Please arrive 10 minutes early. Bring this confirmation and your\n"
        "vehicle registration. Need to change plans? Visit 'My Appointments'\n"
        "in the app to reschedule or cancel — no phone call required.\n"
    )


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/car-service.png", width=72)
    st.title("AutoCare Pro")
    st.caption("AI-assisted service booking")

    st.divider()
    st.markdown("**Active Agents**")
    st.markdown("""
    <span class="agent-badge badge-crew">🤖 ARIA — CrewAI</span><br>
    <span class="agent-badge badge-autogen">📅 APEX — AutoGen</span><br>
    <span class="agent-badge badge-sk">🧠 NEXUS — Semantic Kernel</span><br>
    <span class="agent-badge badge-voice">🎙️ VOICE — SoundHound AI</span>
    """, unsafe_allow_html=True)
    st.caption(
        "ℹ️ These agent names describe the app's simulated multi-agent "
        "workflow (used for demos). No live calls are made to OpenAI, "
        "CrewAI, AutoGen, Semantic Kernel, or SoundHound in this build."
    )

    st.divider()
    customer_pages = ["💬 Chat", "📅 Book Appointment", "🗂️ My Appointments"]
    staff_pages = ["👤 CRM Lookup", "📞 Phone Simulation", "📊 Dashboard", "➕ Customer Directory"]

    if not st.session_state.staff_authenticated:
        with st.expander("🔐 Staff / Admin login"):
            pw = st.text_input("Passcode", type="password", key="staff_pw")
            if st.button("Log in"):
                staff_passcode = os.environ.get("STAFF_PASSCODE", "changeme")
                if pw == staff_passcode:
                    st.session_state.staff_authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect passcode.")
    else:
        st.success("Staff mode active")
        if st.button("Log out of staff mode"):
            st.session_state.staff_authenticated = False
            st.rerun()

    available_pages = customer_pages + (staff_pages if st.session_state.staff_authenticated else [])
    page = st.radio("Navigate", available_pages, label_visibility="collapsed")

    st.divider()
    st.caption("v2.1 · Streamlit + FastAPI")

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h2 style="margin:0">🚗 AutoCare Pro — Book Your Service in Minutes</h2>
    <p style="margin:4px 0 0 0; opacity:.8; font-size:.9rem">
        Chat with ARIA, book an appointment, and manage it anytime — no phone call needed.
    </p>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: CHAT
# ══════════════════════════════════════════════════════════════════════════════
if page == "💬 Chat":
    st.subheader("💬 Chat with ARIA")

    phone_input = st.text_input(
        "Your phone number (optional — helps us recognise you)",
        placeholder="+91-9876543210",
        key="phone_input_chat"
    )

    for role, text, agent in st.session_state.chat_history:
        if role == "user":
            st.markdown(f'<div class="chat-user">👤 <b>You</b><br>{text}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-bot">🤖 <b>{agent}</b><br>{text}</div>', unsafe_allow_html=True)

    col_msg, col_send, col_clear = st.columns([6, 1, 1])
    with col_msg:
        user_msg = st.text_input("Message", placeholder="e.g. Hi, I need an oil change", label_visibility="collapsed", key="chat_input")
    with col_send:
        send = st.button("Send ➤", width='stretch')
    with col_clear:
        if st.button("🗑️", width='stretch', help="Clear chat"):
            st.session_state.chat_history = []
            st.rerun()

    if send and user_msg.strip():
        phone = phone_input.strip() or None
        st.session_state.chat_history.append(("user", user_msg, "You"))

        with st.spinner("ARIA is thinking…"):
            result = orchestrator.handle_chat_interaction(user_msg, phone)

        primary = result.get("primary_response", {})
        msg = primary.get("message", "I'm here to help!")
        agent_label = primary.get("agent", "ARIA (CrewAI)")
        st.session_state.chat_history.append(("bot", msg, agent_label))

        if "booking" in result and result["booking"].get("success"):
            booking = result["booking"]
            bk_msg = booking.get("message", "Appointment booked!")
            st.session_state.chat_history.append(("bot", bk_msg, "APEX (AutoGen Booking)"))
            if primary.get("customer_id"):
                st.session_state.my_customer_id = primary["customer_id"]

        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: BOOK APPOINTMENT
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📅 Book Appointment":
    st.subheader("📅 Book an Appointment")

    customer = None
    if st.session_state.staff_authenticated:
        mode = st.radio(
            "Book as", ["My own account", "Look up any customer (staff)"],
            horizontal=True, key="book_mode"
        )
    else:
        mode = "My own account"

    if mode == "Look up any customer (staff)":
        customers = orchestrator.crm.customers
        if not customers:
            st.warning("No customers found yet.")
        else:
            customer_options = {f"{c.name} ({cid})": cid for cid, c in customers.items()}
            selected_label = st.selectbox("Select Customer", list(customer_options.keys()))
            customer_id = customer_options[selected_label]
            customer = customers[customer_id]
            st.info(f"🚗 {customer.vehicle_year} {customer.vehicle_make} {customer.vehicle_model}  \n"
                    f"📞 {customer.phone}  \n⭐ {customer.loyalty_points} loyalty pts")
    else:
        customer = identify_customer_widget("book")

    if customer:
        customer_id = customer.id
        col1, col2 = st.columns(2)
        with col1:
            service_options = [s.value for s in ServiceType]
            service_choice = st.selectbox("Service Type", service_options)
        with col2:
            preferred_date = st.date_input(
                "Preferred Date",
                value=datetime.now().date() + timedelta(days=1),
                min_value=datetime.now().date()
            )
            date_str = preferred_date.strftime("%Y-%m-%d")

        available_slots = orchestrator.crm.get_available_slots(date_str)
        if available_slots:
            preferred_time = st.selectbox("Available Time Slots", available_slots)
        else:
            st.error("No slots available on this date. Please choose another date.")
            preferred_time = None

        if st.button("✅ Confirm Booking", type="primary") and preferred_time:
            with st.spinner("APEX is processing your booking…"):
                service_enum = ServiceType(service_choice)
                result = orchestrator.booking_agent.orchestrate_booking(
                    customer_id, service_enum, date_str, preferred_time
                )

            if result.get("success"):
                apt_raw = result.get("appointment") or result.get("confirmation") or {}
                service = apt_raw.get("service") or apt_raw.get("service_type")
                service_display = service.value if isinstance(service, ServiceType) else (str(service) if service else "—")
                date = apt_raw.get("date") or apt_raw.get("scheduled_date")
                time = apt_raw.get("time") or apt_raw.get("scheduled_time")
                advisor = apt_raw.get("advisor") or "TBD"
                est_cost = apt_raw.get("estimated_cost") or apt_raw.get("cost") or apt_raw.get("cost_inr")
                if isinstance(est_cost, (int, float)):
                    est_cost_str = f"₹{est_cost:,.0f}"
                elif isinstance(est_cost, str) and est_cost.startswith("₹"):
                    est_cost_str = est_cost
                elif isinstance(est_cost, str) and est_cost.replace(",", "").replace(".", "").isdigit():
                    try:
                        est_cost_str = f"₹{int(float(est_cost)):,.0f}"
                    except Exception:
                        est_cost_str = est_cost
                else:
                    est_cost_str = "N/A"

                st.success(f"**Booking Confirmed!** Appointment ID: `{apt_raw.get('id')}`")
                cols = st.columns(4)
                cols[0].metric("Service", service_display)
                cols[1].metric("Date & Time", f"{date or 'N/A'} {time or ''}")
                cols[2].metric("Advisor", advisor)
                cols[3].metric("Estimated Cost", est_cost_str)
                st.balloons()

                apt_obj = orchestrator.crm.appointments.get(apt_raw.get("id"))
                if apt_obj:
                    receipt = build_receipt_text(apt_obj, customer)
                    st.download_button(
                        "⬇️ Download confirmation", data=receipt,
                        file_name=f"{apt_obj.id}_confirmation.txt", mime="text/plain"
                    )
                st.caption("You can view, reschedule, or cancel this booking anytime under **🗂️ My Appointments**.")
            else:
                st.error(f"Booking failed: {result.get('error', 'Unknown error')}")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: MY APPOINTMENTS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗂️ My Appointments":
    st.subheader("🗂️ My Appointments")
    customer = identify_customer_widget("myapts")

    if customer:
        appts = sorted(
            orchestrator.crm.get_customer_appointments(customer.id),
            key=lambda a: (a.scheduled_date, a.scheduled_time),
        )
        if not appts:
            st.info("You don't have any appointments yet. Head to **📅 Book Appointment** to schedule one.")
        for apt in appts:
            service = apt.service_type.value if isinstance(apt.service_type, ServiceType) else str(apt.service_type)
            status = apt.status.value if hasattr(apt.status, "value") else apt.status
            css_class = "apt-card"
            if status == "cancelled":
                css_class += " apt-cancelled"
            elif status == "completed":
                css_class += " apt-completed"

            with st.container():
                st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1:
                    st.markdown(f"**{service}**  \n`{apt.id}`")
                with c2:
                    st.markdown(f"📅 {apt.scheduled_date} at {apt.scheduled_time}  \n👨‍🔧 {apt.advisor}")
                with c3:
                    st.markdown(f"💰 ₹{apt.estimated_cost:,.0f}  \n**Status:** {status.title()}")

                if status == "confirmed":
                    ac1, ac2, ac3 = st.columns(3)
                    with ac1:
                        receipt = build_receipt_text(apt, customer)
                        st.download_button(
                            "⬇️ Receipt", data=receipt, file_name=f"{apt.id}_confirmation.txt",
                            mime="text/plain", key=f"dl_{apt.id}"
                        )
                    with ac2:
                        with st.popover("🔁 Reschedule"):
                            new_date = st.date_input(
                                "New date", value=datetime.strptime(apt.scheduled_date, "%Y-%m-%d").date(),
                                min_value=datetime.now().date(), key=f"resched_date_{apt.id}"
                            )
                            new_date_str = new_date.strftime("%Y-%m-%d")
                            slots = orchestrator.crm.get_available_slots(new_date_str)
                            if apt.scheduled_date == new_date_str and apt.scheduled_time not in slots:
                                slots = [apt.scheduled_time] + slots
                            if slots:
                                new_time = st.selectbox("New time", slots, key=f"resched_time_{apt.id}")
                                if st.button("Confirm reschedule", key=f"resched_btn_{apt.id}"):
                                    res = orchestrator.crm.reschedule_appointment(apt.id, new_date_str, new_time)
                                    if res.get("success"):
                                        st.success("Appointment rescheduled!")
                                        st.rerun()
                                    else:
                                        st.error(res.get("error", "Could not reschedule."))
                            else:
                                st.warning("No slots available that day.")
                    with ac3:
                        if st.button("❌ Cancel", key=f"cancel_{apt.id}"):
                            st.session_state[f"confirm_cancel_{apt.id}"] = True
                        if st.session_state.get(f"confirm_cancel_{apt.id}"):
                            st.warning("Are you sure you want to cancel this appointment?")
                            cc1, cc2 = st.columns(2)
                            if cc1.button("Yes, cancel it", key=f"confirm_yes_{apt.id}"):
                                orchestrator.crm.cancel_appointment(apt.id)
                                st.session_state[f"confirm_cancel_{apt.id}"] = False
                                st.success("Appointment cancelled.")
                                st.rerun()
                            if cc2.button("Keep it", key=f"confirm_no_{apt.id}"):
                                st.session_state[f"confirm_cancel_{apt.id}"] = False
                                st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: CRM LOOKUP (staff)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👤 CRM Lookup":
    st.subheader("🧠 CRM Intelligence — NEXUS (Semantic Kernel)")

    customers = orchestrator.crm.customers
    if not customers:
        st.info("No customers yet.")
    else:
        customer_options = {f"{c.name} ({cid})": cid for cid, c in customers.items()}
        selected = st.selectbox("Select Customer", list(customer_options.keys()))
        customer_id = customer_options[selected]

        if st.button("🔍 Run CRM Intelligence Pipeline", type="primary"):
            with st.spinner("NEXUS is analysing the customer profile…"):
                result = orchestrator.crm_agent.run_customer_pipeline(customer_id)

            if result.get("success"):
                profile = result["customer_profile"]
                intel = result["intelligence"]
                recs = result.get("recommendations", [])

                col1, col2, col3 = st.columns(3)
                col1.metric("Customer", profile["name"])
                col2.metric("Vehicle", profile["vehicle"])
                col3.metric("Total Spent", f"₹{intel['total_spent']}")

                col4, col5, col6 = st.columns(3)
                col4.metric("Loyalty Tier", intel["loyalty_tier"])
                col5.metric("Loyalty Points", intel["loyalty_points"])
                col6.metric("VIP Status", "⭐ Yes" if intel["is_vip"] else "No")

                with st.expander("📋 Service History"):
                    history = profile.get("service_history", [])
                    if history:
                        for h in history:
                            st.write(f"• {h}")
                    else:
                        st.write("No service history yet.")

                st.markdown("### 💡 Service Recommendations")
                for rec in recs:
                    priority_color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(rec["priority"], "⚪")
                    st.markdown(
                        f"{priority_color} **{rec['service']}** — {rec['reason']}  \n"
                        f"Estimated cost: **{rec['estimated_cost']}** · Priority: `{rec['priority']}`"
                    )
            else:
                st.error(result.get("error", "CRM lookup failed."))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: PHONE SIMULATION (staff)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📞 Phone Simulation":
    st.subheader("📞 Phone Call Simulation — VOICE Handler")
    st.caption(
        "Simulates an incoming phone call through the voice pipeline: "
        "**STT** → **NLU** → **ARIA** → **TTS**. This is a scripted simulation for demos; "
        "wiring it to a live telephony/voice provider requires additional integration work."
    )

    with st.expander("🎙️ Voice provider configuration", expanded=False):
        st.markdown("""
**Set these environment variables before running (if using SoundHound/Houndify):**
```bash
export SOUNDHOUND_API_KEY="your-api-key"
export SOUNDHOUND_CLIENT_ID="your-client-id"
```
**Capabilities simulated in this demo:**
- Streaming STT with per-word confidence scores
- Automotive-domain vocabulary boost (OBD-II, brake caliper, etc.)
- NLU — intent + entity extraction
- Neural TTS — SSML-driven natural speech
- On-device wake-word ("Hey AutoCare")
- Multi-language: English, Hindi, Telugu, Tamil (auto-detected)
        """)

    caller_phone = st.text_input("Caller Phone Number", value="+91-9988776655")

    st.markdown("**Conversation Script** — one line per customer utterance")
    default_script = (
        "Hello, I need to book a service appointment\n"
        "I need an oil change for my Honda City\n"
        "Tomorrow morning would be great"
    )
    script_text = st.text_area("Customer utterances (one per line)", value=default_script, height=140)

    col_sim, col_wake = st.columns([3, 1])
    with col_sim:
        simulate = st.button("📞 Simulate Call", type="primary", width='stretch')
    with col_wake:
        wake_word_test = st.button("🎙️ Test Wake Word", width='stretch')

    if wake_word_test:
        result = orchestrator.voice_handler.stt_engine.detect_wake_word("Hey AutoCare, book a service")
        if result["triggered"]:
            st.success(f"✅ Wake word **'{result['wake_word']}'** detected! "
                       f"Latency: {result['latency_ms']}ms · On-device: {result['on_device']}")
        else:
            st.info("Wake word not detected. Try including 'Hey AutoCare' in the snippet.")

    if simulate:
        conversation = [line.strip() for line in script_text.splitlines() if line.strip()]

        with st.spinner("Simulating call…"):
            call_result = orchestrator.handle_phone_call(caller_phone, conversation)

        st.success(f"Call ID: `{call_result['call_id']}` · Caller: {call_result['caller']}")
        st.markdown("**Agents used:** " + " → ".join(call_result.get("agents_used", [])))

        flow = call_result.get("flow", [])
        sh_session = None
        for item in flow:
            if "soundhound_session" in item:
                sh_session = item["soundhound_session"]
                break
        if sh_session:
            st.info(
                f"🎙️ **Voice Session:** `{sh_session.get('session_id', 'N/A')}` · "
                f"Language: `{sh_session.get('language', 'en-IN')}` · "
                f"Domain vocab: `{sh_session.get('domain_vocab_loaded', 0)}` terms · "
                f"Target latency: `{sh_session.get('latency_target_ms', 180)}ms`"
            )

        st.markdown("### 📝 Call Transcript")
        for item in call_result.get("flow", []):
            if "greeting" in item:
                st.markdown(f"🤖 **ARIA:** {item['greeting']}")
                if item.get("tts_audio_url"):
                    st.caption(f"🔊 TTS audio: `{item['tts_audio_url']}`")
            elif "spoken_response" in item:
                st.markdown(f"🤖 **ARIA:** {item['spoken_response']}")
                stt = item.get("stt_result", {})
                nlu = item.get("nlu_result", {})
                if stt:
                    conf_colour = "🟢" if stt.get("confidence", 0) >= 0.80 else "🟡" if stt.get("confidence", 0) >= 0.60 else "🔴"
                    st.caption(
                        f"{conf_colour} **STT** confidence={stt.get('confidence')} · "
                        f"lang={stt.get('language_detected', 'en-IN')} · "
                        f"latency={stt.get('streaming_latency_ms')}ms"
                    )
                if nlu:
                    entities_str = ", ".join(f"{k}={v}" for k, v in nlu.get("entities", {}).items()) or "—"
                    st.caption(
                        f"🧠 **NLU** intent=`{nlu.get('primary_intent')}` · "
                        f"entities: {entities_str}"
                    )
                if item.get("tts_audio_url"):
                    st.caption(f"🔊 TTS: `{item['tts_audio_url']}` ({item.get('tts_duration_s', '?')}s)")
            elif item.get("action") == "clarification_request":
                st.warning(f"🎙️ **Low STT confidence** — ARIA asked for clarification: {item.get('spoken_response')}")
            elif "booking_triggered" in item and item.get("result", {}).get("success"):
                booking = item["result"].get("appointment", {})
                st.success(
                    f"✅ **Booking confirmed!** ID: `{booking.get('id')}` — "
                    f"{booking.get('service')} on {booking.get('date')} at {booking.get('time')}"
                )
            elif "transcript" in item:
                avg_conf = item.get("avg_stt_confidence")
                conf_str = f" · Avg STT confidence: `{avg_conf}`" if avg_conf else ""
                st.info(f"📵 Call ended · Duration: {item.get('duration_turns', '?')} turns{conf_str}")

        end_item = next((i for i in call_result.get("flow", []) if "stt_audit_log" in i), None)
        if end_item and end_item.get("stt_audit_log"):
            with st.expander("🔍 STT / NLU Audit Log"):
                for entry in end_item["stt_audit_log"]:
                    st.markdown(f"**Turn {entry['turn']}** — `{entry['timestamp']}`")
                    c1, c2 = st.columns(2)
                    stt = entry.get("stt", {})
                    nlu = entry.get("nlu", {})
                    c1.json({
                        "transcript": stt.get("transcript"),
                        "confidence": stt.get("confidence"),
                        "language": stt.get("language_detected"),
                        "latency_ms": stt.get("streaming_latency_ms"),
                    })
                    c2.json({
                        "intent": nlu.get("primary_intent"),
                        "entities": nlu.get("entities"),
                        "model": nlu.get("nlu_model"),
                    })

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD (staff)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 Dashboard":
    st.subheader("📊 CRM Dashboard")

    dashboard = orchestrator.get_crm_dashboard()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("👥 Total Customers", dashboard["total_customers"])
    k2.metric("📅 Total Appointments", dashboard["total_appointments"])
    k3.metric("✅ Confirmed", dashboard["confirmed_appointments"])
    k4.metric("💰 Revenue Pipeline", f"₹{dashboard['total_revenue_pipeline']:,.0f}")

    st.divider()
    tab_cust, tab_apt = st.tabs(["👥 Customers", "📅 Appointments"])

    with tab_cust:
        customers_data = dashboard["customers"]
        if customers_data:
            import pandas as pd
            df_c = pd.DataFrame(customers_data)
            df_c.columns = [c.replace("_", " ").title() for c in df_c.columns]
            st.dataframe(df_c, width='stretch', hide_index=True)
        else:
            st.info("No customers yet.")

    with tab_apt:
        appointments_data = dashboard["appointments"]
        if appointments_data:
            import pandas as pd
            df_a = pd.DataFrame(appointments_data)

            def colour_status(val):
                colours = {
                    "confirmed": "background-color:#dcfce7",
                    "pending": "background-color:#fef9c3",
                    "cancelled": "background-color:#fee2e2",
                    "completed": "background-color:#e0f2fe",
                }
                return colours.get(val, "")
            df_a.columns = [c.replace("_", " ").title() for c in df_a.columns]
            st.dataframe(df_a.style.map(colour_status, subset=["Status"]),
                         width='stretch', hide_index=True)
        else:
            st.info("No appointments yet.")

    if st.button("🔄 Refresh Dashboard"):
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: CUSTOMER DIRECTORY (staff)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "➕ Customer Directory":
    st.subheader("➕ Add / Look Up Customers")

    with st.form("new_customer_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full Name *", placeholder="Arjun Mehta")
            phone = st.text_input("Phone *", placeholder="+91-9876543210")
            email = st.text_input("Email *", placeholder="arjun@email.com")
        with col2:
            make = st.text_input("Vehicle Make *", placeholder="Toyota")
            model = st.text_input("Vehicle Model *", placeholder="Innova")
            year = st.number_input("Vehicle Year *", min_value=1990,
                                    max_value=datetime.now().year + 1,
                                    value=2021, step=1)

        submitted = st.form_submit_button("➕ Add Customer", type="primary")

    if submitted:
        errors = []
        if not all([name.strip(), phone.strip(), email.strip(), make.strip(), model.strip()]):
            errors.append("Please fill in all required fields.")
        if phone.strip() and not PHONE_RE.match(phone.strip()):
            errors.append("That doesn't look like a valid phone number.")
        if email.strip() and not EMAIL_RE.match(email.strip()):
            errors.append("Please enter a valid email address.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            customer = orchestrator.crm.create_customer(
                name.strip(), phone.strip(), email.strip(), make.strip(), model.strip(), int(year)
            )
            st.success(f"✅ Customer ready! ID: **{customer.id}**")
            st.json({
                "id": customer.id, "name": customer.name,
                "phone": customer.phone, "email": customer.email,
                "vehicle": f"{customer.vehicle_year} {customer.vehicle_make} {customer.vehicle_model}"
            })

    st.divider()
    st.markdown("### 👥 All Customers")
    customers = orchestrator.crm.customers
    if customers:
        import pandas as pd
        rows = [{
            "ID": c.id, "Name": c.name, "Phone": c.phone, "Email": c.email,
            "Vehicle": f"{c.vehicle_year} {c.vehicle_make} {c.vehicle_model}",
            "Loyalty Pts": c.loyalty_points,
        } for c in customers.values()]
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
    else:
        st.info("No customers yet.")
