from server import get_catalog, get_dataset_schema, get_dataset_sample, run_sql_query

def test_prototype():
    print("=== Testing lakehouse://catalog ===")
    cat = get_catalog()
    print(cat[:800] + "...\n")
    
    print("=== Testing lakehouse://dataset/bronze/bronze.football_sample/schema ===")
    sch = get_dataset_schema("bronze", "bronze.football_sample")
    print(sch[:800] + "...\n")
    
    print("=== Testing lakehouse://dataset/bronze/bronze.football_sample/sample ===")
    smp = get_dataset_sample("bronze", "bronze.football_sample")
    print(smp[:800] + "...\n")

    print("=== Testing SQL Query Tool ===")
    res = run_sql_query("SELECT HomeTeam, AwayTeam, FTHG, FTAG FROM bronze_football_sample WHERE FTHG > 4 LIMIT 3")
    print(res)

if __name__ == "__main__":
    test_prototype()
