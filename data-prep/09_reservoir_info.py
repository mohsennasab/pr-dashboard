"""Reservoir information cards.

Figures below were taken from the USGS sedimentation survey publications
listed with each reservoir. Capacities are reported by USGS in million
cubic meters and converted here to acre feet (1 Mm3 = 810.71 acre feet).
"""

from common import VECTORS, save_json

ACRE_FEET_PER_MM3 = 810.71

FACTS = {
    "guineo": {
        "built": 1931,
        "original_mm3": 2.29,
        "surveys": [{"year": 1986, "mm3": 2.03}, {"year": 2001, "mm3": 1.89}],
        "note": "Toro Negro Hydroelectric Project. Lost about 17.5 percent of its"
        " original capacity by 2001.",
        "report": "USGS WRI 03-4093, Sedimentation Survey of Lago El Guineo,"
        " October 2001",
        "report_url": "https://pubs.usgs.gov/publication/wri034093",
    },
    "matrullas": {
        "built": 1934,
        "original_mm3": 3.71,
        "surveys": [{"year": 2001, "mm3": 3.08}],
        "note": "Toro Negro Hydroelectric Project. Published drainage area is"
        " 11.45 square kilometers. Lost about 17 percent of its original"
        " capacity by 2001.",
        "report": "USGS WRI 03-4102, Sedimentation Survey of Lago de Matrullas,"
        " December 2001",
        "report_url": "https://pubs.usgs.gov/publication/wri034102",
    },
    "guayabal": {
        "built": 1913,
        "original_mm3": 11.82,
        "surveys": [{"year": 2017, "mm3": 4.98}],
        "note": "Irrigation reservoir on the Rio Jacaguas. The 2017 survey found"
        " about 58 percent of the original capacity lost. Long term loss rate"
        " about 0.065 million cubic meters per year for 1972 to 2017.",
        "report": "USGS SIM 3442, Sedimentation Survey of Lago Guayabal,"
        " December 2017",
        "report_url": "https://pubs.usgs.gov/publication/sim3442",
    },
    "guayo": {
        "built": 1956,
        "original_mm3": 19.20,
        "surveys": [{"year": 1997, "mm3": 16.57}],
        "note": "Largest reservoir in the Southwestern Puerto Rico Project."
        " Sediment trapping efficiency about 97 percent. Sediment yield about"
        " 857 megagrams per square kilometer per year.",
        "report": "USGS WRI 99-4053, Sedimentation Survey of Lago Guayo,"
        " October 1997",
        "report_url": "https://pubs.usgs.gov/publication/wri994053",
    },
    "loco": {
        "built": 1951,
        "original_mm3": 2.40,
        "surveys": [{"year": 1986, "mm3": 1.43}, {"year": 2000, "mm3": 0.87}],
        "note": "Southwestern Puerto Rico Project. Lost 64 percent of its"
        " original capacity by 2000, the fastest relative loss among the six"
        " reservoirs.",
        "report": "USGS WRI 01-4187, Sedimentation Survey of Lago Loco,"
        " March 2000",
        "report_url": "https://pubs.usgs.gov/publication/wri014187",
    },
    "lucchetti": {
        "built": 1952,
        "original_mm3": 20.35,
        "surveys": [
            {"year": 1986, "mm3": 15.84},
            {"year": 2000, "mm3": 11.88},
            {"year": 2014, "mm3": 10.21},
        ],
        "note": "Southwestern Puerto Rico Project, on the Rio Yauco. About half"
        " of the original capacity was lost by 2014. Long term loss rate about"
        " 0.17 million cubic meters per year.",
        "report": "USGS SIM 3364, Sedimentation Survey of Lago Lucchetti,"
        " September 2013 to May 2014",
        "report_url": "https://pubs.usgs.gov/publication/sim3364",
    },
}


def main() -> None:
    for facts in FACTS.values():
        facts["original_acft"] = round(facts["original_mm3"] * ACRE_FEET_PER_MM3)
        for survey in facts["surveys"]:
            survey["acft"] = round(survey["mm3"] * ACRE_FEET_PER_MM3)
        latest = facts["surveys"][-1]
        facts["latest_year"] = latest["year"]
        facts["pct_lost"] = round(
            100 * (1 - latest["mm3"] / facts["original_mm3"])
        )
    save_json(FACTS, VECTORS / "reservoir_info.json")


if __name__ == "__main__":
    main()
