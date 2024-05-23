document.addEventListener('DOMContentLoaded', () => {
    const satIDMapping = {
        1: 'GS-1a',
        2: 'GS-2',
        3: 'GS-2AP01',
        4: 'GS-2AP02',
        5: 'GS-2AP03',
        6: 'GS-2BP01',
        7: 'GS-2BP02',
        8: 'HT1-A',
        9: 'HT1-B',
        10: 'HT1-C',
        11: 'HT1-D',
        12: 'AS02',
        13: 'AS03',
        14: 'GS-NY01'
    };

    const satIDCheckboxes = document.getElementById('satIDCheckboxes');
    for (let i = 1; i <= 14; i++) {
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `satID_${i}`;
        checkbox.value = i;
        checkbox.name = 'satID';

        const label = document.createElement('label');
        label.htmlFor = `satID_${i}`;
        label.textContent = satIDMapping[i];

        satIDCheckboxes.appendChild(checkbox);
        satIDCheckboxes.appendChild(label);
    }

    const submitButton = document.getElementById('submitButton');

    submitButton.addEventListener('click', () => {
        const start = document.getElementById('start').value;
        const end = document.getElementById('end').value;
        const selectedSatIDs = Array.from(document.querySelectorAll('input[name="satID"]:checked')).map(cb => cb.value);

        const satID = selectedSatIDs.join(',');

        const requestData = {
            start: new Date(start).toISOString(),
            end: new Date(end).toISOString(),
            date: new Date().toISOString().split('T')[0],
            satID: satID
        };

        fetch('http://172.16.10.56:7877/spiderlingdailyreport', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            populateFlightControlTable(data.satellites);
            populateSubsystemTable(data.satellites);
            populateLevelTable(data.satellites);
            populateOrbitTable(data.satellites);
        })
        .catch(error => console.error('Error:', error));
    });

    function populateFlightControlTable(satellites) {
        const flightControlTableBody = document.getElementById('flightControlTable').getElementsByTagName('tbody')[0];
        flightControlTableBody.innerHTML = '';

        let prevSatID = '';
        let rowspanCount = 0;
        let firstCell = null;

        satellites.forEach(satellite => {
            satellite.flightcontrol.forEach((task, index) => {
                const row = flightControlTableBody.insertRow();

                if (prevSatID !== satellite.satID) {
                    if (firstCell) {
                        firstCell.rowSpan = rowspanCount;
                    }
                    prevSatID = satellite.satID;
                    rowspanCount = 1;

                    firstCell = row.insertCell();
                    firstCell.textContent = satellite.satID;
                } else {
                    rowspanCount++;
                }

                Object.values(task).forEach((val, i) => {
                    const cell = row.insertCell();
                    if (i === 0 && firstCell) {
                        firstCell.rowSpan = rowspanCount;
                    }
                    cell.textContent = val;
                });
            });
        });

        if (firstCell) {
            firstCell.rowSpan = rowspanCount;
        }
    }

    function populateSubsystemTable(satellites) {
        const subsystemTableBody = document.getElementById('subsystemTable').getElementsByTagName('tbody')[0];
        subsystemTableBody.innerHTML = '';

        satellites.forEach(satellite => {
            for (let subsystem in satellite.subsystem) {
                const row = subsystemTableBody.insertRow();

                const satIDCell = row.insertCell();
                satIDCell.textContent = satellite.satID;

                row.insertCell().textContent = subsystem;
                row.insertCell().textContent = satellite.subsystem[subsystem].count;
            }
        });
    }

    function populateLevelTable(satellites) {
        const levelTableBody = document.getElementById('levelTable').getElementsByTagName('tbody')[0];
        levelTableBody.innerHTML = '';

        satellites.forEach(satellite => {
            for (let subsystem in satellite.level) {
                const row = levelTableBody.insertRow();

                const satIDCell = row.insertCell();
                satIDCell.textContent = satellite.satID;

                row.insertCell().textContent = subsystem;
                row.insertCell().textContent = satellite.level[subsystem].FATAL;
                row.insertCell().textContent = satellite.level[subsystem].CRITICAL;
                row.insertCell().textContent = satellite.level[subsystem].WARNING;
                row.insertCell().textContent = satellite.level[subsystem].INFO;
            }
        });
    }

    function populateOrbitTable(satellites) {
        const orbitTableBody = document.getElementById('orbitTable').getElementsByTagName('tbody')[0];
        orbitTableBody.innerHTML = '';

        satellites.forEach(satellite => {
            const row = orbitTableBody.insertRow();

            const satIDCell = row.insertCell();
            satIDCell.textContent = satellite.satID;

            row.insertCell().textContent = satellite.orbit.p.mse;
            row.insertCell().textContent = satellite.orbit.h.alt;
        });
    }
});
