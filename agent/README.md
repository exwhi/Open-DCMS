Minimal Agent example

Run the simple agent to send a demo payload to the Open-DCMS ingest API:

```bash
python agent/simple_agent.py --tenant demo --source simple-agent --api-url http://localhost:8000/api/v1/ingest --api-key dev-secret
```

Replace with real collectors (sFlow/NetFlow) and implement local cache/mtls as needed for production.