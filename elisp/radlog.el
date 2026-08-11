;;; radlog.el --- RadMachine import entrypoint  -*- lexical-binding: t; -*-

(defgroup radlog nil
  "Import RadMachine activity into an Org logbook."
  :group 'tools)

(require 'json)
(require 'org-id)
(require 'org)
(require 'seq)
(require 'subr-x)

(defconst radlog--library-file
  (or load-file-name buffer-file-name)
  "File from which the radlog library was loaded.")

(defcustom radlog-python-command "python"
  "Python executable used to invoke the radlog CLI."
  :type 'string
  :group 'radlog)

(defcustom radlog-default-user nil
  "Default username passed to the radlog CLI."
  :type '(choice (const :tag "Prompt each time" nil) string)
  :group 'radlog)

(defcustom radlog-target-file nil
  "Fallback Org file that accepted entries will be inserted into."
  :type '(choice (const :tag "Unset" nil) file)
  :group 'radlog)

(defcustom radlog-target-heading nil
  "Fallback heading under which accepted entries will be inserted.

If nil, append to the end of `radlog-target-file'."
  :type '(choice (const :tag "Append to end of file" nil) string)
  :group 'radlog)

(defcustom radlog-destination-map nil
  "Alist mapping entry types to insertion destinations.

Each entry is of the form:
  (ENTRY-TYPE :file \"/path/to/file.org\" :id \"ORG-ID\")

ENTRY-TYPE may also be the string \"default\" to provide a catch-all route
for candidates whose specific `entry_type' is not mapped."
  :type '(alist :key-type string :value-type plist)
  :group 'radlog)

(defcustom radlog-save-with-hooks nil
  "Whether radlog should run save hooks when writing reviewed entries.

When nil, radlog saves with `before-save-hook' and `after-save-hook'
temporarily disabled. This avoids expensive or blocking hook chains during
review accept/skip/defer flows."
  :type 'boolean
  :group 'radlog)

(defvar radlog--candidate-queue nil)
(defvar radlog--deferred-candidates nil)
(defvar radlog--total-candidates 0)
(defvar radlog--current-candidate-index 0)

(defvar-local radlog--current-candidate nil)
(defvar-local radlog--target-file nil)
(defvar-local radlog--target-id nil)
(defvar-local radlog--draft-start-marker nil)
(defvar-local radlog--draft-end-marker nil)

(define-derived-mode radlog-review-mode org-mode "Radlog-Review"
  "Major mode for reviewing imported RadMachine entries."
  (setq-local header-line-format
              (format "radlog review %d/%d: C-c C-c keep  C-c C-k remove  C-c C-d defer"
                      radlog--current-candidate-index
                      radlog--total-candidates)))

(define-key radlog-review-mode-map (kbd "C-c C-c") #'radlog-review-accept)
(define-key radlog-review-mode-map (kbd "C-c C-k") #'radlog-review-skip)
(define-key radlog-review-mode-map (kbd "C-c C-d") #'radlog-review-defer)

;;;###autoload
(defun radlog-import-radmachine (start end user)
  "Start a RadMachine import for START, END, and USER."
  (interactive
   (list
    (radlog--read-date "Start date: ")
    (radlog--read-date "End date: ")
    (read-string "Username: " radlog-default-user)))
  (let* ((target-file (or radlog-target-file
                          (read-file-name "Target Org file: " nil nil nil nil
                                          (lambda (file)
                                            (string-suffix-p ".org" file)))))
         (payload (radlog--run-cli start end user))
         (candidates (alist-get 'candidates payload)))
    (setq radlog--candidate-queue candidates)
    (setq radlog--deferred-candidates nil)
    (setq radlog--total-candidates (length candidates))
    (setq radlog--current-candidate-index 0)
    (if (null candidates)
        (message "radlog: no candidates returned")
      (radlog--show-next-candidate target-file))))

(defun radlog-review-accept ()
  "Keep the current in-place draft and move to the next candidate."
  (interactive)
  (unless radlog--current-candidate
    (user-error "No current radlog candidate"))
  (radlog--save-review-buffer)
  (radlog--advance-review "Kept" (current-buffer) radlog--target-file))

(defun radlog-review-skip ()
  "Remove the current in-place draft and move to the next candidate."
  (interactive)
  (unless radlog--current-candidate
    (user-error "No current radlog candidate"))
  (let ((skip-count (radlog--maybe-skip-future-like-candidates radlog--current-candidate)))
    (when (> skip-count 0)
      (setq radlog--total-candidates (- radlog--total-candidates skip-count))))
  (radlog--remove-current-draft)
  (radlog--advance-review "Skipped" (current-buffer) radlog--target-file))

(defun radlog-review-defer ()
  "Remove the current in-place draft and defer the candidate for later."
  (interactive)
  (unless radlog--current-candidate
    (user-error "No current radlog candidate"))
  (push radlog--current-candidate radlog--deferred-candidates)
  (radlog--remove-current-draft)
  (radlog--advance-review "Deferred" (current-buffer) radlog--target-file))

(defun radlog--run-cli (start end user)
  "Run the radlog CLI for START, END, and USER and return parsed JSON."
  (let* ((default-directory (radlog--project-root))
         (args (list "-m" "radlog.cli"
                     "--collect" "qa-candidates"
                     "--start" start
                     "--end" end
                     "--user" user))
         (stdout (generate-new-buffer " *radlog-stdout*"))
         (stderr-file (make-temp-file "radlog-stderr-")))
    (unwind-protect
        (let ((status (apply #'call-process radlog-python-command nil (list stdout stderr-file) nil args)))
          (unless (eq status 0)
            (with-temp-buffer
              (insert-file-contents stderr-file)
              (error "radlog CLI failed: %s" (string-trim (buffer-string)))))
          (with-current-buffer stdout
            (json-parse-string (buffer-string)
                               :object-type 'alist
                               :array-type 'list
                               :null-object nil
                               :false-object nil)))
      (kill-buffer stdout)
      (ignore-errors (delete-file stderr-file)))))

(defun radlog--show-next-candidate (fallback-file)
  "Insert the next candidate into its target Org buffer for in-place review."
  (if-let* ((candidate (pop radlog--candidate-queue))
            (destination (radlog--resolve-destination candidate fallback-file))
            (target-file (car destination))
            (target-id (cdr destination))
            (buffer (find-file-noselect target-file)))
      (with-current-buffer buffer
        (setq radlog--current-candidate-index
              (1+ radlog--current-candidate-index))
        (unless (derived-mode-p 'org-mode)
          (org-mode))
        (when (radlog--duplicate-group-key-p (alist-get 'group_key candidate))
          (unless (y-or-n-p
                   (format "radlog duplicate detected for %s in %s. Insert anyway? "
                           (alist-get 'group_key candidate)
                           (abbreviate-file-name target-file)))
            (user-error "radlog insertion cancelled for duplicate %s"
                        (alist-get 'group_key candidate))))
        (widen)
        (let ((text (or (alist-get 'rendered_org candidate)
                        (format "%S" candidate)))
              start
              end)
          (save-excursion
            (radlog--goto-id target-id)
            (setq text (radlog--adjust-heading-level
                        text
                        (1+ (org-outline-level))))
            (org-end-of-subtree t t)
            (unless (bolp)
              (insert "\n"))
            (setq start (point))
            (insert text)
            (unless (string-suffix-p "\n" text)
              (insert "\n"))
            (setq end (point)))
          (radlog-review-mode)
          (setq-local radlog--current-candidate candidate)
          (setq-local radlog--target-file target-file)
          (setq-local radlog--target-id target-id)
          (setq-local radlog--draft-start-marker (copy-marker start))
          (setq-local radlog--draft-end-marker (copy-marker end t))
          (narrow-to-region start end)
          (goto-char (point-min))
          (pop-to-buffer buffer)
          (message "radlog: C-c C-c keep, C-c C-k remove, C-c C-d defer")))
    (message "radlog complete: %d deferred" (length radlog--deferred-candidates))))

(defun radlog--advance-review (action review-buffer fallback-file)
  "Advance to the next candidate after ACTION.

REVIEW-BUFFER is the buffer to close. FALLBACK-FILE is kept for destination
resolution."
  (when (buffer-live-p review-buffer)
    (with-current-buffer review-buffer
      (radlog--clear-review-state)))
  (message "radlog: %s" action)
  (condition-case err
      (radlog--show-next-candidate fallback-file)
    (error
     (user-error "radlog stopped while opening the next candidate: %s"
                 (error-message-string err)))))

(defun radlog--maybe-skip-future-like-candidates (candidate)
  "Optionally skip queued candidates similar to CANDIDATE.

Return the number of additional queued candidates removed."
  (let* ((entry-type (alist-get 'entry_type candidate))
         (title (alist-get 'title candidate))
         (matching-count (radlog--count-queued-candidates-of-type entry-type)))
    (if (or (null entry-type) (= matching-count 0))
        0
      (if (y-or-n-p
           (format "radlog: skip %d future %s entr%s too? "
                   matching-count
                   (or title entry-type)
                   (if (= matching-count 1) "y" "ies")))
          (radlog--drop-queued-candidates-of-type entry-type)
        0))))

(defun radlog--count-queued-candidates-of-type (entry-type)
  "Return the number of queued candidates with ENTRY-TYPE."
  (length
   (seq-filter
    (lambda (candidate)
      (equal entry-type (alist-get 'entry_type candidate)))
    radlog--candidate-queue)))

(defun radlog--drop-queued-candidates-of-type (entry-type)
  "Remove queued candidates with ENTRY-TYPE and return the number removed."
  (let ((original-count (length radlog--candidate-queue)))
    (setq radlog--candidate-queue
          (seq-remove
           (lambda (candidate)
             (equal entry-type (alist-get 'entry_type candidate)))
           radlog--candidate-queue))
    (- original-count (length radlog--candidate-queue))))

(defun radlog--remove-current-draft ()
  "Delete the current in-place draft from the buffer and save."
  (unless (and radlog--draft-start-marker radlog--draft-end-marker)
    (user-error "No current radlog draft markers"))
  (let ((inhibit-read-only t)
        (start (marker-position radlog--draft-start-marker))
        (end (marker-position radlog--draft-end-marker)))
    (widen)
    (delete-region start end)
    (radlog--save-review-buffer)))

(defun radlog--save-review-buffer ()
  "Save current buffer for radlog review operations.

If `radlog-save-with-hooks' is nil, save without running save hooks."
  (if radlog-save-with-hooks
      (save-buffer)
    (let ((before-save-hook nil)
          (after-save-hook nil))
      (basic-save-buffer nil))))

(defun radlog--clear-review-state ()
  "Restore the current buffer after an in-place radlog review step."
  (widen)
  (setq header-line-format nil)
  (setq-local radlog--current-candidate nil)
  (setq-local radlog--target-file nil)
  (setq-local radlog--target-id nil)
  (when radlog--draft-start-marker
    (set-marker radlog--draft-start-marker nil))
  (when radlog--draft-end-marker
    (set-marker radlog--draft-end-marker nil))
  (setq-local radlog--draft-start-marker nil)
  (setq-local radlog--draft-end-marker nil)
  (org-mode))

(defun radlog--resolve-destination (candidate fallback-file)
  "Resolve insertion destination for CANDIDATE.

Return a cons cell of (FILE . ID)."
  (let* ((entry-type (alist-get 'entry_type candidate))
         (route (or (cdr (assoc entry-type radlog-destination-map))
                    (cdr (assoc "default" radlog-destination-map))))
         (file (plist-get route :file))
         (id (plist-get route :id)))
    (cond
     ((and file id)
      (cons file id))
     ((and fallback-file radlog-target-heading)
      (user-error
       "radlog destination for %s must be configured with `radlog-destination-map' using :file and :id, or add a \"default\" route"
       entry-type))
     (t
      (user-error
       "radlog destination for %s is not configured; set `radlog-destination-map' with :file and :id, or add a \"default\" route"
       entry-type)))))

(defun radlog--goto-id (id)
  "Move point to the Org heading identified by ID."
  (let ((location (org-id-find id t)))
    (unless location
      (user-error "radlog could not find Org ID %s" id))
    (goto-char location)
    (org-back-to-heading t)))

(defun radlog--adjust-heading-level (text target-level)
  "Rewrite Org headings in TEXT so the first heading uses TARGET-LEVEL stars."
  (with-temp-buffer
    (insert text)
    (goto-char (point-min))
    (when (re-search-forward "^\\(\\*+\\) " nil t)
      (let ((delta (- target-level (length (match-string 1)))))
        (goto-char (point-min))
        (while (re-search-forward "^\\(\\*+\\) " nil t)
          (let ((new-level (+ (length (match-string 1)) delta)))
            (replace-match (concat (make-string (max 1 new-level) ?*) " ") t t)))))
    (buffer-string)))

(defun radlog--duplicate-group-key-p (group-key)
  "Return non-nil if GROUP-KEY already exists in the current buffer."
  (when group-key
    (save-excursion
      (goto-char (point-min))
      (re-search-forward
       (format "^:RM_GROUP_KEY: %s$" (regexp-quote group-key))
       nil
       t))))

(defun radlog--read-date (prompt)
  "Read a date with PROMPT using Org date input and return YYYY-MM-DD."
  (org-read-date nil nil nil prompt nil nil nil))

(defun radlog--project-root ()
  "Return the radlog source checkout containing the Python package."
  (or (and radlog--library-file
           (locate-dominating-file
            (file-name-directory radlog--library-file)
            (lambda (directory)
              (file-exists-p
               (expand-file-name "radlog/cli.py" directory)))))
      default-directory))

(provide 'radlog)

;;; radlog.el ends here
