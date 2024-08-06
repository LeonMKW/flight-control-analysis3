const data = {
    "mission_quality": {
        "33357": {
            "mission_id": "33357",
            "starting": 1715734891551.0,
            "ending": 1715735506024.0,
            "telemetry": {
                "0": {
                    "start": 1715734885000.0,
                    "end": 1715735466000.0
                },
                "1": {
                    "start": 1715735471000.0,
                    "end": 1715735471000.0
                },
                "2": {
                    "start": 1715735472000.0,
                    "end": 1715735504000.0
                }
            },
            "uplink": {
                "2": {
                    "duration": 569,
                    "lock_status": 1,
                    "start": 1715734897000.0,
                    "end": 1715735466000.0
                },
                "3": {
                    "duration": 32,
                    "lock_status": 1,
                    "start": 1715735472000.0,
                    "end": 1715735504000.0
                }
            }
        },
        "33363": {
            "mission_id": "33363",
            "starting": 1715764818606.0,
            "ending": 1715765445163.0,
            "telemetry": {
                "0": {
                    "start": 1715764821000.0,
                    "end": 1715765052000.0
                },
                "1": {
                    "start": 1715765056000.0,
                    "end": 1715765056000.0
                },
                "2": {
                    "start": 1715765057000.0,
                    "end": 1715765445000.0
                }
            },
            "uplink": {
                "1": {
                    "duration": 231,
                    "lock_status": 1,
                    "start": 1715764821000.0,
                    "end": 1715765052000.0
                },
                "2": {
                    "duration": 389,
                    "lock_status": 1,
                    "start": 1715765056000.0,
                    "end": 1715765445000.0
                }
            }
        },
        "33366": {
            "mission_id": "33366",
            "starting": 1715776281858.0,
            "ending": 1715776906496.0,
            "telemetry": {
                "0": {
                    "start": 1715776282000.0,
                    "end": 1715776913000.0
                }
            },
            "uplink": {
                "2": {
                    "duration": 622,
                    "lock_status": 1,
                    "start": 1715776288000.0,
                    "end": 1715776910000.0
                }
            }
        },
        "33370": {
            "mission_id": "33370",
            "starting": 1715820274909.0,
            "ending": 1715820838420.0,
            "telemetry": {
                "0": {
                    "start": 1715820346000.0,
                    "end": 1715820841000.0
                }
            },
            "uplink": {
                "1": {
                    "duration": 130,
                    "lock_status": 1,
                    "start": 1715820346000.0,
                    "end": 1715820476000.0
                },
                "3": {
                    "duration": 190,
                    "lock_status": 1,
                    "start": 1715820489000.0,
                    "end": 1715820679000.0
                },
                "5": {
                    "duration": 146,
                    "lock_status": 1,
                    "start": 1715820685000.0,
                    "end": 1715820831000.0
                }
            }
        }
    }
};

const missions = Object.values(data.mission_quality);
const plotsContainer = d3.select("#plots");
const tooltip = d3.select(".tooltip");

const width = 1000;
const height = 100;
const margin = { left: 50, right: 50 };

missions.forEach((mission, i) => {
    const missionDiv = plotsContainer.append("div")
        .attr("class", "plot-container")
        .style("border", "1px solid #ccc")
        .style("padding", "10px")
        .style("margin", "10px 0");

    missionDiv.append("h3").text(`Mission ID: ${mission.mission_id}`);

    const svg = missionDiv.append("svg")
        .attr("width", width)
        .attr("height", height);

    const xScale = d3.scaleLinear()
        .domain([mission.starting, mission.ending])
        .range([margin.left, width - margin.right]);

    svg.append("line")
        .attr("x1", xScale(mission.starting))
        .attr("x2", xScale(mission.ending))
        .attr("y1", height / 2)
        .attr("y2", height / 2)
        .attr("stroke", "grey")
        .attr("stroke-width", 4);

    Object.values(mission.telemetry).forEach(d => {
        svg.append("line")
            .attr("x1", xScale(d.start))
            .attr("x2", xScale(d.end))
            .attr("y1", height / 2)
            .attr("y2", height / 2)
            .attr("stroke", "red")
            .attr("stroke-width", 4)
            .on("mouseover", function(event) {
                tooltip.transition().duration(200).style("opacity", .9);
                tooltip.html(`Telemetry Start: ${new Date(d.start).toLocaleString()}<br/>Telemetry End: ${new Date(d.end).toLocaleString()}`)
                    .style("left", (event.pageX) + "px")
                    .style("top", (event.pageY - 28) + "px");
            })
            .on("mouseout", function() {
                tooltip.transition().duration(500).style("opacity", 0);
            });
    });

    Object.values(mission.uplink).forEach(d => {
        svg.append("line")
            .attr("x1", xScale(d.start))
            .attr("x2", xScale(d.end))
            .attr("y1", height / 2)
            .attr("y2", height / 2)
            .attr("stroke", "green")
            .attr("stroke-width", 4)
            .on("mouseover", function(event) {
                tooltip.transition().duration(200).style("opacity", .9);
                tooltip.html(`Uplink Start: ${new Date(d.start).toLocaleString()}<br/>Uplink End: ${new Date(d.end).toLocaleString()}`)
                    .style("left", (event.pageX) + "px")
                    .style("top", (event.pageY - 28) + "px");
            })
            .on("mouseout", function() {
                tooltip.transition().duration(500).style("opacity", 0);
            });
    });
});
