document.addEventListener('DOMContentLoaded', () => {
    // Mapping of satID to display names
    const satIDMapping = {
        1: 'GS-1a',
        2: 'GS-2',
        3: 'GS-2AP01',
        4: 'GS-2AP02',
        5: 'GS-2AP03',
        6: 'GS-2BP01',
        7: 'GS-2BP02',
        12: 'AS02',
        13: 'AS03',
        14: 'GS-NY01'
    };

    // Dynamically create checkboxes for satID (1 to 14)
    const satIDCheckboxes = document.getElementById('satIDCheckboxes');
    for (let i = 1; i <= 14; i++) {
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `satID_${i}`;
        checkbox.value = i;
        checkbox.name = 'satID';

        const label = document.createElement('label');
        label.htmlFor = `satID_${i}`;
        label.textContent = satIDMapping[i];  // Use the mapped display name

        satIDCheckboxes.appendChild(checkbox);
        satIDCheckboxes.appendChild(label);
    }

    const submitButton = document.getElementById('submitButton');

    submitButton.addEventListener('click', () => {
        const start = document.getElementById('start').value;
        const end = document.getElementById('end').value;
        const selectedSatIDs = Array.from(document.querySelectorAll('input[name="satID"]:checked')).map(cb => cb.value);

        // Convert selectedSatIDs to a comma-separated string
        const satID = selectedSatIDs.join(',');

        const requestData = {
            start: new Date(start).toISOString(),
            end: new Date(end).toISOString(),
            date: new Date().toISOString().split('T')[0], // assuming 'date' is today's date
            satID: satID
        };

        fetch('/spiderlingdailyreport', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            populateTaskTable(data.task_list);
            populateCompanyTable(data.company_name_counts);
        })
        .catch(error => console.error('Error:', error));
    });

    // Function to populate the task table
    function populateTaskTable(taskList) {
        const taskTableBody = document.getElementById('taskTable').getElementsByTagName('tbody')[0];
        taskTableBody.innerHTML = ''; // Clear existing rows

        taskList.forEach(task => {
            const row = taskTableBody.insertRow();

            Object.values(task).forEach(val => {
                const cell = row.insertCell();
                cell.textContent = val;
            });
        });
    }

    // Function to populate the company name counts table
    function populateCompanyTable(companyList) {
        const companyTableBody = document.getElementById('companyTable').getElementsByTagName('tbody')[0];
        companyTableBody.innerHTML = ''; // Clear existing rows

        companyList.forEach(company => {
            const row = companyTableBody.insertRow();

            Object.values(company).forEach(val => {
                const cell = row.insertCell();
                cell.textContent = val;
            });
        });
    }
});
