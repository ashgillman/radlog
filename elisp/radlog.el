;;; radlog.el --- RadMachine import entrypoint  -*- lexical-binding: t; -*-

;; Minimal entrypoint for the review/import workflow.

(defgroup radlog nil
  "Import RadMachine activity into an Org logbook."
  :group 'tools)

(defcustom radlog-python-command "python"
  "Python executable used to invoke the radlog CLI."
  :type 'string
  :group 'radlog)

(defcustom radlog-config-file "config.toml"
  "Config file passed to the radlog CLI."
  :type 'file
  :group 'radlog)

;;;###autoload
(defun radlog-import-radmachine (start end user)
  "Start a RadMachine import for START, END, and USER.

This currently collects input and confirms the command shape. Review and
insertion flow will be added once the Python side emits real candidates."
  (interactive
   (list
    (read-string "Start date (YYYY-MM-DD): ")
    (read-string "End date (YYYY-MM-DD): ")
    (read-string "Username: ")))
  (message
   "radlog import pending: %s -m radlog.cli --config %s --start %s --end %s --user %s"
   radlog-python-command
   radlog-config-file
   start
   end
   user))

(provide 'radlog)

;;; radlog.el ends here
