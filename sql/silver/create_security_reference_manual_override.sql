DROP TABLE IF EXISTS silver.security_reference_manual_override;

CREATE TABLE silver.security_reference_manual_override (
    ticker VARCHAR PRIMARY KEY,
    instrument_type VARCHAR NOT NULL,
    resolution_source VARCHAR NOT NULL,
    resolution_notes VARCHAR
);

INSERT INTO silver.security_reference_manual_override
VALUES
    (
        'TI.A',
        'Common Stock',
        'manual_reference_override',
        'Historical Telecom Italia class-share listing; classified as ordinary/common equity.'
    ),
    (
        'XAN',
        'Common Stock',
        'manual_reference_override',
        'Exantas Capital Corp. listed common equity; provider/reference metadata insufficiently descriptive.'
    );
