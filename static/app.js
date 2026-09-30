let rooms = [];
const expandedParticipants = new Set();

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
    const match = String(title).match(/\b(CS|BS|OS)\s*0*(\d+)\b/i);

    if (!match) {
        return "OUTRAS";
    }

    return `${match[1].toUpperCase()}${Number(match[2])}`;
}


function groupNumber(group) {
    const match = group.match(/^(CS|BS|OS)(\d+)$/i);

    if (!match) {
        return 999999;
    }

    const prefixOrder = {
        CS: 0,
        BS: 1,
        OS: 2
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
                <div class="participants-cell" data-idx="${esc(room.meet_url)}">
                    <b class="clickable-count">${room.participants}</b>
                    <span>Participantes</span>
                </div>

                <div>
                    <b class="${room.recording ? "recording-on" : ""}">
                        ${room.recording ? "SIM" : "NÃO"}
                    </b>
                    <span>Gravando</span>
                </div>
            </div>

            <ul class="participants-list ${expandedParticipants.has(room.meet_url) ? "" : "hidden"}">
                ${
                    (room.participant_names && room.participant_names.length)
                        ? room.participant_names.map(n => `<li>${esc(n)}</li>`).join("")
                        : "<li>Nenhum participante</li>"
                }
            </ul>

            ${
                room.error
                    ? `<p class="error">${esc(room.error)}</p>`
                    : ""
            }

            <p class="meet-link-text">${esc(room.meet_url)}</p>

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

    const mainRoom = group.items.find(isMainRoom);

    const formadorInfo = group.items.find(r => r.formador);
    const formadorHtml = formadorInfo
        ? `<p class="formador ${formadorInfo.formador_presente ? "formador-presente" : "formador-ausente"}">
                👤 ${esc(formadorInfo.formador)}
                ${
                    formadorInfo.formador_presente
                        ? `— presente em <strong>${esc(formadorInfo.formador_localizacao)}</strong>`
                        : "— não detectado em nenhuma sala do grupo"
                }
            </p>`
        : "";

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

                    ${
                        mainRoom
                            ? `<p class="meet-link-text group-link">${esc(mainRoom.meet_url)}</p>`
                            : ""
                    }

                    ${formadorHtml}
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

const DIA_HOJE = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"][new Date().getDay()];

function render() {
    const q = document
        .querySelector("#search")
        .value
        .trim()
        .toLowerCase();

    const soHoje = document.querySelector("#hoje").checked;

    const filtered = rooms.filter(room => {
        const group = getGroup(room.title);

        const matchesText = (
            room.title.toLowerCase().includes(q) ||
            group.toLowerCase().includes(q)
        );

        const matchesDia = !soHoje || room.day === DIA_HOJE;

        return matchesText && matchesDia;
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

        document.querySelector("#active_rooms").textContent =
            status.active_rooms ?? status.active;

        document.querySelector("#active_cells").textContent =
            status.active_cells ?? 0;

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

document
    .querySelector("#hoje")
    .addEventListener("change", render);

document
    .querySelector("#rooms")
    .addEventListener("click", event => {
        const cell = event.target.closest(".participants-cell");

        if (!cell) {
            return;
        }

        const list = cell
            .closest("article")
            .querySelector(".participants-list");

        if (list) {
            list.classList.toggle("hidden");

            const url = cell.dataset.idx;

            if (expandedParticipants.has(url)) {
                expandedParticipants.delete(url);
            } else {
                expandedParticipants.add(url);
            }
        }
    });

refresh();

setInterval(refresh, 3000);