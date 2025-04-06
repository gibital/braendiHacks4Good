Erstellt im Rahmen vom Hack4SocialGood Hackathon 2025.

Ziel des Projekts war eine KI-gestützte Lösung für die Arbeitsplanung für den Wohnbereich von Brändi zu entwickeln.

Unser Prototyp verwendet die Open Source library "Operations Research Tools" von Google statt eines neuronalen Netzwerks, und orientiert sich an folgendem guide: https://developers.google.com/optimization/scheduling/employee_scheduling

Das git repository teilt sich auf in eine command line app und eine web Applikation.

Command line app:
- app.py

web Applikation:
- templates/index.html
- scheduling.py
- flaskServer.py
- runtime.txt
- requirements.txt
- Procfile (für deployment mit Heroku)
