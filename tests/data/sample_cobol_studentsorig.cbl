01 StudentRecord.
   88 EndOfStudentFile     VALUE HIGH-VALUES.
   02 StudentID            PIC X(7).
   02 FILLER               PIC X(23).

FD TransRecords.
01 TransRecord.
   88 EndOfTransFile       VALUE HIGH-VALUES.
   02 TransStudentID       PIC X(7).
   02 FILLER               PIC X(23).

FD NewStudentRecords.
01 NewStudentRecord        PIC X(30).