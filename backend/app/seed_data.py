"""
Seeds the database with a starter set of realistic, messy complaint
examples. Covers: sarcasm, bundled multi-issue messages, praise mistaken
for complaints, hedged food-safety language, test/QA noise, emoji-only
low-signal messages, driver-originated complaints, and legal/compliance
issues (MRP overcharge), plus Hinglish and tone/urgency-mismatch cases.

Seeded complaints are inserted UNCLASSIFIED (no Classification rows) so
that the live Groq API classification pipeline is what the reviewer
actually exercises from the dashboard ("Classify" / "Classify All").
"""
from sqlalchemy.orm import Session

from . import models

SEED_COMPLAINTS = [
    # -- sarcasm --
    dict(
        channel="app",
        customer_identifier="priya.sharma",
        complainant_type="customer",
        raw_message=(
            "Wow, only 90 minutes late for a '20 minute delivery' promise. "
            "Truly impressive work, UrbanDash. My biryani is now a science "
            "experiment. 10/10 would NOT recommend."
        ),
    ),
    dict(
        channel="twitter_dm",
        customer_identifier="@rohit_speaks",
        complainant_type="customer",
        raw_message=(
            "cool cool cool, love that you charged me twice for one order "
            "and support just keeps sending me the same copy-paste reply. "
            "very cool system you have here."
        ),
    ),
    # -- bundled multi-issue --
    dict(
        channel="email",
        customer_identifier="ananya.k@gmail.com",
        complainant_type="customer",
        raw_message=(
            "Hi, two things — first, order #48213 arrived an hour late and "
            "the packet was leaking oil all over my hallway. Second, I was "
            "charged ₹499 for a plan I never signed up for, please refund "
            "and cancel it. This is honestly getting ridiculous with how "
            "often billing messes up."
        ),
    ),
    dict(
        channel="app",
        customer_identifier="vikram.singh",
        complainant_type="customer",
        raw_message=(
            "My order was completely wrong (got someone else's groceries, "
            "no idea whose) AND when I called the driver to ask about it he "
            "was extremely rude and started shouting at me on the phone. "
            "I want a refund and I think that driver needs to be looked into."
        ),
    ),
    # -- praise mistaken for complaint --
    dict(
        channel="app",
        customer_identifier="megha.rao",
        complainant_type="customer",
        raw_message=(
            "Just wanted to say the delivery guy today, Suresh, was "
            "amazing — it was pouring rain and he still made sure my food "
            "was dry and warm. Please give him a bonus or something, "
            "seriously impressed."
        ),
    ),
    dict(
        channel="email",
        customer_identifier="karan.mehta@outlook.com",
        complainant_type="customer",
        raw_message=(
            "Not a complaint, just feedback — the new app checkout flow is "
            "so much faster now. Whoever redesigned it, well done. Keep it up!"
        ),
    ),
    # -- hedged food-safety language (should still be high/critical) --
    dict(
        channel="app",
        customer_identifier="sana.iqbal",
        complainant_type="customer",
        raw_message=(
            "hi, this might be nothing and maybe I'm overreacting, but the "
            "chicken in my order today smelled kind of off and there was a "
            "weird greyish tint to it? I didn't eat it just to be safe. "
            "probably fine, just wanted to flag it in case."
        ),
    ),
    dict(
        channel="email",
        customer_identifier="deepak.verma@yahoo.com",
        complainant_type="customer",
        raw_message=(
            "Not sure if this is a big deal or not, but I found what looked "
            "like a small piece of plastic in my curry last night. I didn't "
            "get hurt or anything, just thought someone should know about it, "
            "no rush."
        ),
    ),
    # -- calm tone but genuinely urgent food safety --
    dict(
        channel="app",
        customer_identifier="fatima.noor",
        complainant_type="customer",
        raw_message=(
            "Hello. I wanted to inform you calmly that both my husband and "
            "I have been vomiting since eating the paneer tikka we ordered "
            "two hours ago. We suspect food poisoning. Order #55210. "
            "Please investigate the restaurant."
        ),
    ),
    # -- test / QA noise --
    dict(
        channel="app",
        customer_identifier="qa_test_acct_07",
        complainant_type="customer",
        raw_message="test test 123 ignore this ticket please",
    ),
    dict(
        channel="email",
        customer_identifier="internal-qa@urbandash.test",
        complainant_type="customer",
        raw_message="asdf checking if email ingestion pipeline is working, disregard",
    ),
    # -- emoji-only / low signal --
    dict(
        channel="twitter_dm",
        customer_identifier="@foodie_anon22",
        complainant_type="customer",
        raw_message="😡😡😡",
    ),
    dict(
        channel="app",
        customer_identifier="user_88213",
        complainant_type="customer",
        raw_message="???",
    ),
    dict(
        channel="twitter_dm",
        customer_identifier="@quietkunal",
        complainant_type="customer",
        raw_message="👎",
    ),
    # -- driver-originated complaints --
    dict(
        channel="app",
        customer_identifier="driver_id_3391",
        complainant_type="driver",
        raw_message=(
            "The customer at drop-off today grabbed my arm and screamed at "
            "me for being 5 minutes late, then threatened to 'get me fired' "
            "and followed me back to my bike. I felt genuinely unsafe. "
            "Order #61042."
        ),
    ),
    dict(
        channel="app",
        customer_identifier="driver_id_1187",
        complainant_type="driver",
        raw_message=(
            "Is Sector 21 in Gurugram in our delivery coverage zone now? "
            "I keep getting orders routed there but the app map shows it "
            "greyed out and I'm not sure if I'm supposed to accept them."
        ),
    ),
    dict(
        channel="app",
        customer_identifier="driver_id_5502",
        complainant_type="driver",
        raw_message=(
            "My last three payout cycles have been short by a few hundred "
            "rupees each and I can't figure out why from the app breakdown. "
            "Can someone from finance actually look at my account instead "
            "of the chatbot?"
        ),
    ),
    # -- legal / compliance: MRP overcharge --
    dict(
        channel="email",
        customer_identifier="advocate.suresh@lawmail.com",
        complainant_type="customer",
        raw_message=(
            "I was charged ₹45 for a Coke bottle that clearly states MRP "
            "₹40 printed on the packaging. This is a violation of the "
            "Legal Metrology Act and I want written confirmation this will "
            "be corrected, or I will be filing a consumer complaint."
        ),
    ),
    dict(
        channel="app",
        customer_identifier="ritika.j",
        complainant_type="customer",
        raw_message=(
            "every single item in my cart today was priced above the MRP "
            "printed on the pack itself, by like 5-10 rupees each. that "
            "cannot be legal right? this needs to be looked at seriously."
        ),
    ),
    # -- Hinglish / multilingual --
    dict(
        channel="app",
        customer_identifier="amitabh.g",
        complainant_type="customer",
        raw_message=(
            "yaar order 2 ghante se late hai, driver ka phone bhi nahi lag "
            "raha, bahut ho gaya ab. kal function tha usme khaana late "
            "pahuncha, bilkul embarrassing tha."
        ),
    ),
    dict(
        channel="twitter_dm",
        customer_identifier="@nehaspeaks",
        complainant_type="customer",
        raw_message=(
            "bhai paneer mein baal mila 😭 ye seriously gross hai, kabhi "
            "order nahi karungi is restaurant se dobara. UrbanDash please "
            "restaurant ko check karo."
        ),
    ),
    # -- billing dispute, plain --
    dict(
        channel="app",
        customer_identifier="tanvi.desai",
        complainant_type="customer",
        raw_message=(
            "I was charged for order #71029 which I cancelled within 30 "
            "seconds of placing it. The app shows it as cancelled but my "
            "card was still charged ₹612. Please refund."
        ),
    ),
    # -- order mixup --
    dict(
        channel="app",
        customer_identifier="ishaan.p",
        complainant_type="customer",
        raw_message=(
            "I ordered a vegetarian thali and received a completely "
            "different non-veg order in a bag with someone else's name on "
            "the receipt. I'm vegetarian for religious reasons so this is "
            "a genuine problem, not just a mix-up."
        ),
    ),
    # -- account management --
    dict(
        channel="email",
        customer_identifier="oldaccount.raj@gmail.com",
        complainant_type="customer",
        raw_message=(
            "I've been trying to delete my account for two weeks and "
            "keep getting looped back to a 'contact support' page that "
            "goes nowhere. Please just delete my data and account, GDPR/DPDP "
            "request if needed."
        ),
    ),
    # -- delivery delay, plain --
    dict(
        channel="app",
        customer_identifier="gaurav.n",
        complainant_type="customer",
        raw_message=(
            "Order has been 'out for delivery' for 55 minutes now and the "
            "tracking map hasn't moved at all. Can someone check what's "
            "going on?"
        ),
    ),
    # -- driver safety, different angle: driver reports unsafe road conditions --
    dict(
        channel="app",
        complainant_type="driver",
        customer_identifier="driver_id_9021",
        raw_message=(
            "The delivery point for this apartment complex requires going "
            "down an unlit alley with no phone signal, twice this month "
            "I've felt unsafe delivering there at night. Can we get this "
            "flagged or delivery hours restricted for that address?"
        ),
    ),
    # -- ambiguous / could be read as praise but is actually a complaint (sarcastic praise) --
    dict(
        channel="twitter_dm",
        customer_identifier="@disappointed_diner",
        complainant_type="customer",
        raw_message=(
            "big fan of getting a completely empty bag delivered to my "
            "door and being told 'enjoy your meal' by the app notification. "
            "chef's kiss UrbanDash, chef's kiss."
        ),
    ),
    # -- genuinely short but real complaint, low signal risk --
    dict(
        channel="app",
        customer_identifier="user_44921",
        complainant_type="customer",
        raw_message="never got my order. no refund either. 3rd time this month.",
    ),
    # -- driver complaint about pay/coverage bundled --
    dict(
        channel="app",
        customer_identifier="driver_id_6620",
        complainant_type="driver",
        raw_message=(
            "Two issues — my incentive payout from last week's weekend "
            "bonus never showed up, and also I want to know if the new "
            "Sector 62 zone has been added to my coverage area yet since "
            "I keep getting orders there I can't accept."
        ),
    ),
    # -- test noise, different flavor --
    dict(
        channel="twitter_dm",
        customer_identifier="@qa_bot_dm_test",
        complainant_type="customer",
        raw_message="automation test message - please disregard - ticket_id=TEST-001",
    ),
]


def run_seed(db: Session) -> None:
    existing = db.query(models.Complaint).count()
    if existing > 0:
        return

    for item in SEED_COMPLAINTS:
        db.add(
            models.Complaint(
                channel=item["channel"],
                customer_identifier=item["customer_identifier"],
                complainant_type=item["complainant_type"],
                raw_message=item["raw_message"],
                status=models.ComplaintStatus.open,
            )
        )
    db.commit()
