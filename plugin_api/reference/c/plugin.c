/* Dependency-free C reference for the API-1 command conformance profile. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_MESSAGE (16U * 1024U * 1024U)

static const char *INITIALIZE_RESULT =
    "{\"plugin_id\":\"org.manuskript.reference.c\","
    "\"api_version\":1,\"protocol_version\":1,\"contributions\":[{"
    "\"declaration\":{\"$kind\":\"record\","
    "\"name\":\"contribution_declaration\",\"version\":1,\"fields\":{"
    "\"kind\":{\"$kind\":\"enum\",\"name\":\"contribution_kind\","
    "\"value\":\"command\"},\"descriptor\":{\"$kind\":\"record\","
    "\"name\":\"extension_descriptor\",\"version\":1,\"fields\":{"
    "\"id\":\"org.manuskript.reference.c.command\","
    "\"name\":\"C conformance command\",\"description\":\"\","
    "\"icon\":\"\",\"extensions\":{\"$kind\":\"tuple\",\"items\":[]}}},"
    "\"configuration\":{\"$kind\":\"map\",\"items\":{}}}},"
    "\"operations\":[\"invoke\"]}]}";

static const char *COMMAND_RESULT =
    "{\"$kind\":\"map\",\"items\":{\"language\":\"c\","
    "\"message\":\"Manuskript API 1\"}}";

static int send_result(long id, const char *result) {
    int needed = snprintf(NULL, 0,
        "{\"jsonrpc\":\"2.0\",\"id\":%ld,\"result\":%s}", id, result);
    char *payload;
    if (needed < 0) return 0;
    payload = malloc((size_t)needed + 1U);
    if (!payload) return 0;
    snprintf(payload, (size_t)needed + 1U,
        "{\"jsonrpc\":\"2.0\",\"id\":%ld,\"result\":%s}", id, result);
    printf("Content-Length: %d\r\n\r\n", needed);
    if (fwrite(payload, 1, (size_t)needed, stdout) != (size_t)needed) {
        free(payload);
        return 0;
    }
    free(payload);
    return fflush(stdout) == 0;
}

static int request_id(const char *message, long *id) {
    const char *field = strstr(message, "\"id\":");
    char *end;
    if (!field) return 0;
    *id = strtol(field + 5, &end, 10);
    return end != field + 5;
}

static int read_message(char **message) {
    char header[8192];
    size_t length = 0;
    int found = 0;
    while (fgets(header, sizeof(header), stdin)) {
        if (strcmp(header, "\r\n") == 0) break;
        if (sscanf(header, "Content-Length: %zu", &length) == 1) found++;
    }
    if (feof(stdin)) return 0;
    if (found != 1 || length < 2 || length > MAX_MESSAGE) return -1;
    *message = malloc(length + 1U);
    if (!*message) return -1;
    if (fread(*message, 1, length, stdin) != length) {
        free(*message);
        return -1;
    }
    (*message)[length] = '\0';
    return 1;
}

int main(void) {
    for (;;) {
        char *message = NULL;
        long id = 0;
        int status = read_message(&message);
        int ok = 1;
        if (status == 0) return 0;
        if (status < 0) return 2;
        if (strstr(message, "\"method\":\"exit\"")) {
            free(message);
            return 0;
        }
        if (strstr(message, "\"method\":\"initialize\"")) {
            ok = request_id(message, &id) && send_result(id, INITIALIZE_RESULT);
        } else if (strstr(message, "\"method\":\"contribution/call\"")) {
            ok = request_id(message, &id) && send_result(id, COMMAND_RESULT);
        } else if (
            strstr(message, "\"method\":\"deactivate\"") ||
            strstr(message, "\"method\":\"shutdown\"")
        ) {
            ok = request_id(message, &id) && send_result(id, "null");
        }
        free(message);
        if (!ok) return 3;
    }
}
