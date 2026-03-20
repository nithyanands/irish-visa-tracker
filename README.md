# 🇮🇪 Irish Visa Tracker

Free community-powered Irish visa application tracker.

**[Live App →](https://irish-visa-tracker.streamlit.app)**

## What it does

- Check if your IRL number has been decided (New Delhi + Dublin ISD, updated daily)
- See how your wait compares to similar applicants (community data)
- Get a predicted decision date based on your embassy received date
- Email alert when your decision appears
- Post-decision checklist: VFS collection, eICR, GNIB registration

## Deploy your own

1. Fork this repo
2. Create free accounts: [Streamlit Cloud](https://share.streamlit.io) + [Supabase](https://supabase.com)
3. Run `schema.sql` in Supabase SQL Editor
4. Add Supabase credentials to Streamlit Cloud secrets
5. Deploy — live in 5 minutes

See `.streamlit/secrets.toml.template` for the secrets format.

## Revenue model

This tool is free. It's supported by:
- Optional Ko-fi tips from users who found it helpful
- UPI donations (Indian users)
- Affiliate links in the post-approval checklist (Wise, Niyo, travel insurance)
- No ads. No data sales. No subscriptions.

## Expand it

This is the starter version. Planned additions:
- More embassy support (Ankara, Abu Dhabi, Beijing)
- PDF arrival guide for approved students
- Sponsorship from legitimate student-focused services
- Enhanced community analytics as data grows

## Built with

Streamlit · Supabase · BeautifulSoup · pandas
Data: Irish Embassy New Delhi ODS · Dublin ISD HTML

Not affiliated with the Irish Embassy or any immigration authority.
