let rooms = [];

function esc(value) {
    return String(value ?? "").replace(
        /[&<>'"]/g,
        c => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "'": "&#39;",
            '"': "&quot;"
        }[c])
    );
}

function getGroup(title) {
    const match = String(title).match(/\b(BS|OS)\s*0*(\d+)\b/i);

    if (!match) {
        return "OUTRAS";
    }

    return `${match[1].toUpperCase()}${Number(match[2])}`;
}


function groupNumber(group) {
    const match = group.match(/^(BS|OS)(\d+)$/i);

    if (!match) {
        return 999999;
    }

    const prefixOrder = {
        BS: 0,
        OS: 1
    };

    const prefix = match[1].toUpperCase();
    const number = Number(match[2]);

    return (prefixOrder[prefix] ?? 99) * 10000 + number;
}

function isMainRoom(room) {
    return /^\s*Sala\b/i.test(room.title);
}

function cellNumber(room) {
    const match = room.title.match(
        /C[eé]lula\s*0*(\d+)/i
    );

    return match ? Number(match[1]) : 0;
}

function sortRooms(a, b) {
    if (isMainRoom(a) && !isMainRoom(b)) {
        return -1;
    }

    if (!isMainRoom(a) && isMainRoom(b)) {
        return 1;
    }

    return cellNumber(a) - cellNumber(b);
}

function buildGroups(data) {
    const groups = new Map();

    for (const room of data) {
        const group = getGroup(room.title);

        if (!groups.has(group)) {
            groups.set(group, []);
        }

        groups.get(group).push(room);
    }

    return [...groups.entries()]
        .sort(
            ([a], [b]) =>
                groupNumber(a) - groupNumber(b)
        )
        .map(([name, items]) => ({
            name,
            items: items.sort(sortRooms)
        }));
}

function renderRoom(room) {
    return `
        <article class="
            room
            ${room.active ? "active" : ""}
            ${isMainRoom(room) ? "principal" : ""}
        ">
            <div class="room-head">
                <div>
                    <h3>${esc(room.title)}</h3>
                    <small>${esc(room.day)}</small>
                </div>

                <span class="
                    status
                    ${room.active ? "on" : "off"}
                ">
                    ${room.active ? "ATIVA" : "INATIVA"}
                </span>
            </div>

            <div class="metrics">
                <div>
                    <b>${room.participants}</b>
                    <span>Participantes</span>
                </div>

                <div>
                    <b class="${room.recording ? "recording-on" : ""}">
                        ${room.recording ? "SIM" : "NÃO"}
                    </b>
                    <span>Gravando</span>
                </div>
            </div>

            ${
                room.error
                    ? `<p class="error">${esc(room.error)}</p>`
                    : ""
            }

            <a
                class="join"
                href="${esc(room.meet_url)}"
                target="_blank"
                rel="noopener noreferrer"
            >
                Entrar
            </a>
        </article>
    `;
}

function renderGroup(group, index) {
    const active = group.items.filter(
        room => room.active
    ).length;

    const participants = group.items.reduce(
        (total, room) =>
            total + Number(room.participants || 0),
        0
    );

    const recording = group.items.filter(
        room => room.recording
    ).length;

    // Uma cor diferente para cada BS.
    const hue = (210 + index * 43) % 360;

    return `
        <section
            class="room-group"
            style="--hue: ${hue}"
        >
            <div class="group-header">
                <div>
                    <h2>${esc(group.name)}</h2>

                    <span>
                        ${group.items.length} reuniões
                    </span>
                </div>

                <div class="group-summary">
                    <span>
                        <strong>${active}</strong>
                        ativas
                    </span>

                    <span>
                        <strong>${participants}</strong>
                        pessoas
                    </span>

                    <span>
                        <strong>${recording}</strong>
                        gravando
                    </span>
                </div>
            </div>

            <div class="group-rooms">
                ${group.items.map(renderRoom).join("")}
            </div>
        </section>
    `;
}

function render() {
    const q = document
        .querySelector("#search")
        .value
        .trim()
        .toLowerCase();

    const filtered = rooms.filter(room => {
        const group = getGroup(room.title);

        return (
            room.title.toLowerCase().includes(q) ||
            group.toLowerCase().includes(q)
        );
    });

    const groups = buildGroups(filtered);

    document.querySelector("#rooms").innerHTML =
        groups
            .map((group, index) =>
                renderGroup(group, index)
            )
            .join("");
}

async function refresh() {
    try {
        const [roomsResponse, statusResponse] =
            await Promise.all([
                fetch("/api/rooms"),
                fetch("/api/status")
            ]);

        rooms = await roomsResponse.json();

        const status = await statusResponse.json();

        document.querySelector("#active").textContent =
            status.active;

        document.querySelector("#participants").textContent =
            status.participants;

        document.querySelector("#recording").textContent =
            status.recording;

        // Agora mostra a quantidade de BS, e não 70 links.
        document.querySelector("#total").textContent =
            new Set(
                rooms.map(room => getGroup(room.title))
            ).size;

        document.querySelector("#updated").textContent =
            `Atualizado: ${
                new Date().toLocaleTimeString("pt-BR")
            }`;

        render();

    } catch (error) {
        console.error(error);

        document.querySelector("#updated").textContent =
            "Falha ao consultar backend";
    }
}

document
    .querySelector("#search")
    .addEventListener("input", render);

refresh();

setInterval(refresh, 3000);