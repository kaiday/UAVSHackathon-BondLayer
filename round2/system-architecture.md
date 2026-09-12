# Data Model

Main data models include:
- Catalogs: products detail
- Policy: text
- Promotions:

# Applications

## Dashboard

Dashboard is the app merchant uses the most. It manages the merchants' catalog and policy and promotions. 

It allows onboard by uploading catalog as a csv sheet, policy and promotions as txt file. 

It has intelligent feature to suggest improvement on catalog and policy.

It has a dashboards analytics page just for demo purpose, no data populated.

## Demo Chat App

Our solution includes mainly 2 things: Onboarding merchant data and UCP integration (with our new loyalty extension layer). The onboarding step can be demoable easily via dashboard application GUI. However, UCP integration is harder to demo. Thus we need this demo chat app to demo our integration.

This chat app must have the mock shopping agent, representing industry shopping agents such as ChatGPT. Its system prompt must be neutral and represent the decision making strategy similar to real shopping agent.

This app allow switching bondlayer (extension) on or off to show the benefits of our layer on the merchant's product's ranking.

This app also show more detail logs to show the evidence of our work, including UCP integration, loyalty layer, policies applied, user identify fetched via UCP, etc. 

# Feature assignment

- Manh: dashboard
- Hieu: RAG for dashboard intelligence and DAO
- Bach: Demo Chat App, including UCP integration and loyalty layer

