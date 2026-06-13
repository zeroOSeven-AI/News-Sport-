import os
import yaml
import subprocess

# Lista svih tvojih YAML datoteka koje želiš testirati
yaml_files = [
    "cleanup.yml",
    "rss_autosport.yaml",
    "rss_f1_official.yaml",
    "rss_gp1.yaml",
    "rss_motosport.yaml",
    "scrape_bild.yaml",
    "scrape_espn.yaml",
    "scrape_marca.yaml",
    "scrape_sn.yml"
]

def pokreni_naredbe_iz_yaml(ime_filea):
    putanja = os.path.join(".github", "workflows", ime_filea)
    
    if not os.path.exists(putanja):
        print(f"⚠️ [MATE LOG] Preskačem: {ime_filea} (Datoteka ne postoji na putanji {putanja})")
        return

    print(f"\n{"="*60}")
    print(f"📖 ČITAM YAML WORKFLOW: {ime_filea}")
    print(f"{"="*60}")

    try:
        with open(putanja, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Prolazimo kroz poslove (jobs) i korake (steps) unutar YAML-a
        jobs = data.get("jobs", {})
        for job_name, job_data in jobs.items():
            steps = job_data.get("steps", [])
            for step in steps:
                # Tražimo 'run' naredbe (gdje se pokreću python skripte)
                if "run" in step:
                    step_name = step.get("name", "Naredba")
                    run_command = step["run"].strip()

                    # Preskačemo git naredbe i instalacije ovisnosti jer testiramo lokalno samo skripte
                    if "git " in run_command or "pip " in run_command or "playwright install" in run_command:
                        continue

                    print(f"▶️ Pokrećem korak [{step_name}]:")
                    print(f"  💻 Naredba iz YAML-a: {run_command}\n")

                    # Pokretanje izvučene naredbe unutar VS Code konzole
                    # Podržava i višelinijske naredbe iz YAML-a
                    rezultat = subprocess.run(run_command, shell=True)

                    if rezultat.returncode == 0:
                        print(f"\n✅ [console.log] Uspješno izvršeno za {ime_filea}!")
                    else:
                        print(f"\n❌ [console.log] GREŠKA prilikom pokretanja naredbe iz {ime_filea}!")

    except Exception as e:
        print(f"❌ [console.log] Kritična greška pri čitanju {ime_filea}: {e}")

if __name__ == "__main__":
    print("🚀 Pokrećem lokalnu simulaciju GitHub Actions YAML datoteka u VS Codeu...\n")
    
    for yml in yaml_files:
        pokreni_naredbe_iz_yaml(yml)
        
    print("\n🏁 Kraj simulacije. Pregledaj konzolu iznad za statuse!")