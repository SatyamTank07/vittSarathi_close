import urllib.request
import json
import sys

def test_dashboard():
    print("--- Testing Dashboard Mode ---")
    req = urllib.request.Request(
        'http://localhost:8000/api/analyze',
        data=json.dumps({"query": "Give me a fundamental analysis of HDFC Bank"}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            d = json.loads(response.read().decode())
            print('status:          ', d.get('status'))
            print('verdict:         ', d.get('investment_verdict'))
            print('synthesizer:     ', d.get('agent_statuses', {}).get('synthesizer'))
            synth = d.get('synthesis') or {}
            print('exec_summary:    ', str(synth.get('executive_summary',''))[:80])
            print('pillars:         ', list((synth.get('dynamic_investment_pillars') or {}).keys()))
            print('risk_dashboard:  ', synth.get('key_risk_dashboard'))
    except Exception as e:
        print(f"Error: {e}")

def test_chat():
    print("\n--- Testing Chat Mode ---")
    req = urllib.request.Request(
        'http://localhost:8000/api/analyze',
        data=json.dumps({"query": "Why is NIM under pressure for HDFC Bank?"}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            d = json.loads(response.read().decode())
            print('response_type:   ', d.get('response_type'))
            print('synthesizer:     ', d.get('agent_statuses', {}).get('synthesizer'))
            synth = d.get('synthesis') or {}
            print('targeted_answer: ', str(synth.get('targeted_answer',''))[:120])
            print('pillars present: ', bool(synth.get('dynamic_investment_pillars')))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    test_dashboard()
    test_chat()
