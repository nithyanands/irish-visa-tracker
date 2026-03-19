"""
verify.py — run by GitHub Actions to confirm secrets and Supabase connection.
Called before daily_sync.py to catch config problems early with clear output.
"""
import os
import sys

print("=" * 50)
print("Irish Visa Tracker — Environment Verification")
print("=" * 50)

url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_KEY", "")

# Check 1: URL present
print(f"\nSUPABASE_URL set:  {bool(url)}")
if url:
    print(f"  starts with:     {url[:40]}")
else:
    print("ERROR: SUPABASE_URL is empty.")
    print("  Fix: repo Settings > Secrets > Actions > add SUPABASE_URL")
    sys.exit(1)

# Check 2: Key present
print(f"\nSUPABASE_KEY set:  {bool(key)}")
if key:
    print(f"  starts with:     {key[:20]}...")
else:
    print("ERROR: SUPABASE_KEY is empty.")
    print("  Fix: repo Settings > Secrets > Actions > add SUPABASE_SERVICE_KEY")
    sys.exit(1)

# Check 3: URL format
if not url.startswith("https://"):
    print(f"\nERROR: URL must start with https://  — got: {url[:30]}")
    sys.exit(1)

if not url.rstrip("/").endswith(".supabase.co"):
    print(f"\nERROR: URL must end with .supabase.co — got: {url[-30:]}")
    sys.exit(1)

# Normalise — lowercase hostname (Supabase refs are always lowercase)
url_clean = url.rstrip("/").lower()
print(f"\nURL normalised:    {url_clean}")

# Check 4: supabase package importable
try:
    from supabase import create_client
    print("\nsupabase package:  importable OK")
except ImportError as e:
    print(f"\nERROR: cannot import supabase: {e}")
    print("  Fix: pip install supabase>=2.4.2")
    sys.exit(1)

# Check 5: actual connection
print("\nTesting Supabase connection...")
try:
    sb = create_client(url_clean, key)
    result = sb.table("ods_dates").select("id", count="exact").limit(1).execute()
    count = result.count if result.count is not None else "unknown"
    print(f"  ods_dates table: accessible ({count} rows)")
except Exception as e:
    print(f"\nERROR connecting to Supabase: {e}")
    print("\nCommon causes:")
    print("  - ods_dates table not created (run schema.sql in Supabase SQL Editor)")
    print("  - Wrong service key (use service_role key, not anon key)")
    print("  - Project paused (restore at supabase.com)")
    sys.exit(1)

print("\n" + "=" * 50)
print("All checks passed. Proceeding to sync.")
print("=" * 50)
