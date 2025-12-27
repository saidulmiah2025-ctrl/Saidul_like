# ultra_controlled_update_tokens.py - Respects rate limits and ensures success
import requests
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def read_json_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(filename, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return None

def bulk_token_generation(uidpass_list, api_url, region_name):
    """Try bulk generation first, but with controlled speed"""
    
    # Skip bulk for now - go directly to controlled parallel
    # Bulk method often hits rate limits with large lists
    print(f"🔄 Using controlled parallel processing for {region_name} (avoiding rate limits)")
    return parallel_token_generation(uidpass_list, api_url, region_name)

def parallel_token_generation(uidpass_list, api_url, region_name):
    """Very controlled processing to minimize failures"""
    
    def generate_single_token(item):
        url = f"{api_url}?uid={item['uid']}&password={item['password']}"
        max_retries = 2  # Increased retries
        
        for attempt in range(max_retries):
            try:
                # Longer delay between requests
                base_delay = 2  # 1s, 1.5s, 2s, 2.5s, 3s
                time.sleep(base_delay)
                
                response = requests.get(url, timeout=20)  # Longer timeout
                
                if response.status_code == 429:  # Rate limited
                    wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s, 40s, 80s
                    print(f"Rate limited for UID {item['uid']}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                if response.status_code >= 500:  # Server errors
                    wait_time = 3 * (attempt + 1)
                    print(f"Server error for UID {item['uid']}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                if data.get("token") and data["token"] != "N/A":
                    return {"token": data["token"], "uid": item['uid']}
                else:
                    if attempt < max_retries - 1:
                        print(f"No token for UID {item['uid']}, retrying in {base_delay}s...")
                        continue
                    else:
                        print(f"No valid token for UID {item['uid']} ({region_name}) after {max_retries} attempts")
                        return {"error": "No token after retries", "uid": item['uid']}
                        
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 5 * (attempt + 1)
                    print(f"Timeout for UID {item['uid']}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"TIMEOUT UID {item['uid']} ({region_name}) after {max_retries} attempts")
                    return {"error": "Timeout after retries", "uid": item['uid']}
                    
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)
                    print(f"Network error for UID {item['uid']}, retrying in {wait_time}s: {str(e)[:50]}...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"NETWORK ERROR UID {item['uid']} ({region_name}) after {max_retries} attempts: {e}")
                    return {"error": f"Network error: {str(e)[:100]}", "uid": item['uid']}
            
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)
                    print(f"Unknown error for UID {item['uid']}, retrying in {wait_time}s: {str(e)[:50]}...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"UNKNOWN ERROR UID {item['uid']} ({region_name}) after {max_retries} attempts: {e}")
                    return {"error": f"Unknown error: {str(e)[:100]}", "uid": item['uid']}
                    
        return {"error": "Max retries exceeded", "uid": item['uid']}
    
    successful_tokens = []
    failed_uids = []
    
    # Reduce to only 5 concurrent workers for very conservative approach
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_item = {executor.submit(generate_single_token, item): item for item in uidpass_list}
        
        completed = 0
        for future in as_completed(future_to_item):
            completed += 1
            try:
                result = future.result()
                if result and "token" in result:
                    successful_tokens.append({"token": result["token"]})
                    print(f"SUCCESS ({region_name}): {len(successful_tokens)}/{len(uidpass_list)} - UID: {result['uid']}")
                else:
                    failed_uids.append(result)
                    print(f"FAILED ({region_name}): UID {result['uid']} - {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                item = future_to_item[future]
                failed_uids.append({"error": str(e), "uid": item['uid']})
                print(f"EXCEPTION for UID {item['uid']} ({region_name}): {e}")
            
            # Progress indicator every 10 completions
            if completed % 5 == 0:
                success_rate = (len(successful_tokens) / completed) * 100
                print(f"PROGRESS ({region_name}): {completed}/{len(uidpass_list)} processed, {success_rate:.1f}% success rate")
    
    # Detailed summary for this region
    success_rate = (len(successful_tokens) / len(uidpass_list)) * 100
    print(f"\n=== {region_name} FINAL SUMMARY ===")
    print(f"Total processed: {len(uidpass_list)}")
    print(f"Successful: {len(successful_tokens)} ({success_rate:.1f}%)")
    print(f"Failed: {len(failed_uids)} ({100-success_rate:.1f}%)")
    
    if failed_uids:
        print(f"\nFailed UIDs for {region_name}:")
        for i, failed in enumerate(failed_uids):
            print(f"  {i+1}. UID {failed['uid']}: {failed.get('error', 'Unknown')}")
            if i >= 19:  # Show max 20 failed UIDs
                remaining = len(failed_uids) - 20
                if remaining > 0:
                    print(f"  ... and {remaining} more failed UIDs")
                break
    
    return successful_tokens

def update_tokens_for_region(uidpass_file, token_file, region_name):
    print(f"\n🚀 Starting {region_name} token generation...")
    start_time = time.time()
    
    # Read UID/Password list
    uidpass_list = read_json_file(uidpass_file)
    if not uidpass_list:
        print(f"❌ Failed to read {uidpass_file}")
        return False
    
    print(f"📊 Processing {len(uidpass_list)} accounts for {region_name}")
    
    # API URL - using your optimized endpoint
    API_URL = "https://jwt-gen-api-forpaglubot.vercel.app/token"
    
    # Get new tokens using ultra-fast method
    new_tokens = bulk_token_generation(uidpass_list, API_URL, region_name)
    
    # Update token file
    if new_tokens:
        try:
            with open(token_file, "w", encoding="utf-8") as f:
                json.dump(new_tokens, f, ensure_ascii=False, indent=2)  # Smaller indent for speed
            
            elapsed = time.time() - start_time
            print(f"✅ {token_file} updated: {len(new_tokens)} tokens in {elapsed:.2f}s")
            print(f"⚡ Speed: {len(new_tokens)/elapsed:.1f} tokens/second")
            return True
        except Exception as e:
            print(f"❌ Error writing {token_file}: {e}")
            return False
    else:
        elapsed = time.time() - start_time
        print(f"❌ No tokens generated for {region_name} in {elapsed:.2f}s")
        return False

def update_all_regions_parallel():
    """Update regions sequentially with longer pauses"""
    
    print("Starting VERY CONTROLLED token generation for all regions...")
    overall_start = time.time()
    
    # Define all regions
    regions = [
        ("uidpass_bd.json", "token_bd.json", "BANGLADESH"),
        ("uidpass_ind.json", "token_ind.json", "INDIA"),
        ("uidpass_br.json", "token_br.json", "BRAZIL")
    ]
    
    results = []
    
    # Process regions one by one with longer delays
    for i, (uidpass_file, token_file, region_name) in enumerate(regions):
        try:
            print(f"\nProcessing region {i+1}/{len(regions)}: {region_name}")
            success = update_tokens_for_region(uidpass_file, token_file, region_name)
            results.append((region_name, success))
            
            # Longer delay between regions to let servers recover
            if i < len(regions) - 1:  # Not the last region
                print(f"Waiting 2 seconds before processing next region...")
                time.sleep(2)
                
        except Exception as e:
            print(f"Region {region_name} failed: {e}")
            results.append((region_name, False))
    
    # Summary
    overall_elapsed = time.time() - overall_start
    successful_regions = sum(1 for _, success in results if success)
    
    print(f"\n=== FINAL RESULTS ===")
    print(f"Total time: {overall_elapsed:.2f} seconds ({overall_elapsed/60:.1f} minutes)")
    print(f"Successful regions: {successful_regions}/{len(regions)}")
    
    for region_name, success in results:
        status = "SUCCESS" if success else "FAILED"
        print(f"  {region_name}: {status}")
    
    if successful_regions < len(regions):
        raise Exception(f"Only {successful_regions}/{len(regions)} regions updated successfully")
    
    print(f"\nAll regions completed in {overall_elapsed/60:.1f} minutes!")
    return True

def update_all_regions_sequential():
    """Fallback sequential method"""
    
    success = True
    overall_start = time.time()
    
    regions = [
        ("uidpass_bd.json", "token_bd.json", "BANGLADESH"),
        ("uidpass_ind.json", "token_ind.json", "INDIA"),
        ("uidpass_br.json", "token_br.json", "BRAZIL")
    ]
    
    for uidpass_file, token_file, region_name in regions:
        if not update_tokens_for_region(uidpass_file, token_file, region_name):
            success = False
    
    overall_elapsed = time.time() - overall_start
    print(f"\n⏱️ Total time: {overall_elapsed:.2f} seconds")
    
    if not success:
        raise Exception("One or more token updates failed")

if __name__ == "__main__":
    try:
        # Try parallel processing first (fastest)
        update_all_regions_parallel()
    except Exception as e:
        print(f"⚠️  Parallel processing failed: {e}")
        print("🔄 Falling back to sequential processing...")
        update_all_regions_sequential()









