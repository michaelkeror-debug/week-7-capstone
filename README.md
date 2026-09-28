# week-7-capstone
week-7-capstone/
├── README.md                    # the template below, filled in

│   ├── cost_model.py            # Deliverable 1
│   ├── sensitivity.py
│   └── cost_model.txt, sensitivity.txt, token_sweep.csv          # $/1k at baseline and at the 10x spike
├── deploy/
│   ├── docker-compose.cost.yml  # Deliverable 2
│   ├── azure_budget_triage.json
│   ├── aws_budget.json
│   └── capstone week 7 evidence
├── levers/
│   ├── cache_triage.py          # Deliverable 3, lever one
│   ├── cache_hitrate.py         # before and after evidence
│   ├── batch_worker.py          # Deliverable 3, lever two
│   └── levers_bench.py -> results/levers_before_after.csv        # the before and after table
├── memo/
│   └── breakeven.py -> results/breakeven.csv -> breakeven_memo.md       # Deliverable 4, 
└── exec/
    └── Afyaplus Cost Memo.pdf            # Deliverable 5