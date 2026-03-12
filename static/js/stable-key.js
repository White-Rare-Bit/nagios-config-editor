/**
 * Stable key format: "source_file|object_type|name"
 *
 * This format is shared with the backend (stable_keys.py).
 * Any change here MUST be coordinated with the backend.
 */

const SEPARATOR = '|';

function build(obj) {
    var nameComponent = obj.display_name ?? obj.name ?? ('idx:' + obj.global_index);
    return obj.source_file + SEPARATOR + obj.object_type + SEPARATOR + nameComponent;
}

function parse(key) {
    if (typeof key !== 'string') { return null; }

    var toParse = key;

    // Handle Base64-encoded keys (backward compat)
    if (toParse.indexOf(SEPARATOR) === -1) {
        try {
            toParse = atob(key);
        } catch (e) {
            return null;
        }
    }

    if (toParse.indexOf(SEPARATOR) === -1) { return null; }

    var parts = toParse.split(SEPARATOR);
    var source_file = parts[0];
    var object_type = parts[1];
    if (!source_file || !object_type) { return null; }

    // Rejoin remaining parts in case the name itself contains the separator
    var name = parts.slice(2).join(SEPARATOR);
    return { source_file: source_file, object_type: object_type, name: name };
}

function findObject(key, objects) {
    var parsed = parse(key);
    if (!parsed) {
        // Fallback: numeric global_index
        var index = parseInt(key, 10);
        if (!isNaN(index)) {
            return objects.find(function(o) { return o.global_index === index; });
        }
        return null;
    }

    var sf = parsed.source_file;
    var ot = parsed.object_type;
    var nm = parsed.name;
    return objects.find(function(o) {
        return o.source_file === sf &&
               o.object_type === ot &&
               ((o.display_name ?? o.name ?? ('idx:' + o.global_index)) === nm);
    });
}

export const StableKey = { SEPARATOR, build, parse, findObject };
